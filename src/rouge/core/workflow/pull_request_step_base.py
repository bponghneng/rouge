"""Shared base class for platform-specific pull request steps."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from typing import ClassVar

from rouge.core.notifications.comments import (
    emit_artifact_comment,
    log_artifact_comment_status,
)
from rouge.core.utils import extract_repo_from_pull_request_url, get_logger
from rouge.core.workflow.artifacts import (
    ArtifactType,
    ComposeRequestArtifact,
    PullRequestArtifactBase,
    PullRequestEntry,
)
from rouge.core.workflow.shared import get_affected_repo_paths, has_branch_delta
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import _emit_and_log, load_and_render_attachment
from rouge.core.workflow.types import StepResult


class PullRequestStepBase(WorkflowStep, ABC):
    """Abstract base for platform-specific pull request / merge request steps.

    Subclasses override the abstract property ``artifact_class`` and define
    the string class attributes below, plus the abstract methods for
    platform-specific CLI operations.
    """

    # ------------------------------------------------------------------
    # Class attributes – subclasses assign these directly, e.g.:
    #   cli_binary = "gh"
    # ------------------------------------------------------------------

    cli_binary: ClassVar[str]
    pat_env_var: ClassVar[str]
    token_env_key: ClassVar[str]
    artifact_slug: ClassVar[ArtifactType]
    platform: ClassVar[str]
    entity_name: ClassVar[str]
    entity_prefix: ClassVar[str]
    output_key_prefix: ClassVar[str]

    # ------------------------------------------------------------------
    # Abstract property
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def artifact_class(self) -> type[PullRequestArtifactBase]:
        """The platform-specific artifact class."""
        ...

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def _list_cmd_args(self, branch_name: str) -> list[str]:
        """Build the command to list existing PRs/MRs for *branch_name*."""
        ...

    @abstractmethod
    def _parse_existing_item(self, item: dict) -> tuple[str, int | None]:
        """Extract ``(url, number)`` from a single JSON list item."""
        ...

    @abstractmethod
    def _create_cmd_args(self, title: str, summary: str, draft: bool) -> list[str]:
        """Build the PR/MR create command."""
        ...

    @abstractmethod
    def _parse_create_output(self, stdout: str) -> tuple[str, int | None] | None:
        """Parse URL and number from create command output.

        Returns ``(url, number)`` or ``None`` if parsing failed.
        """
        ...

    @abstractmethod
    def _post_attachment(self, repo_path: str, number: int, body: str, env: dict[str, str]) -> None:
        """Post or update an attachment comment/note on the PR/MR."""
        ...

    # ------------------------------------------------------------------
    # Concrete properties
    # ------------------------------------------------------------------

    @property
    def is_critical(self) -> bool:
        # PR/MR creation is best-effort - workflow continues on failure
        return False

    # ------------------------------------------------------------------
    # Concrete methods – shared orchestration
    # ------------------------------------------------------------------

    def _check_cli_available(
        self, _context: WorkflowContext, _logger: logging.Logger
    ) -> StepResult | None:
        """Check whether the platform CLI is available.

        Returns a ``StepResult`` to skip the step when the CLI is missing,
        or ``None`` if the check passes (or is not applicable).

        Override in subclasses that need to verify CLI presence.
        """
        return None

    def _check_preconditions(
        self,
        context: WorkflowContext,
        pr_details: list | None,
        logger: logging.Logger,
    ) -> StepResult | None:
        """Validate preconditions for PR/MR creation.

        Returns a ``StepResult`` if a precondition fails (caller should
        return it), or ``None`` if all checks pass.
        """
        if not pr_details:
            skip_msg = f"{self.entity_name} creation skipped: no PR details in context"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": f"{self.output_key_prefix}-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Require at least one entry with a non-empty repo path.
        # Empty-title entries are handled per-repo in the main loop, so we do
        # not gate on title here to avoid duplicating that logic.
        valid_repos = [r for r in pr_details if getattr(r, "repo", None)]
        if not valid_repos:
            skip_msg = f"{self.entity_name} creation skipped: no repositories with PR details"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": f"{self.output_key_prefix}-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Check for PAT environment variable
        if not os.environ.get(self.pat_env_var):
            skip_msg = (
                f"{self.entity_name} creation skipped: "
                f"{self.pat_env_var} environment variable not set"
            )
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": f"{self.output_key_prefix}-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Platform-specific CLI availability check
        return self._check_cli_available(context, logger)

    def _try_adopt_existing(
        self,
        context: WorkflowContext,
        repo_path: str,
        branch_name: str,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
    ) -> bool:
        """Check for and adopt an existing PR/MR for *branch_name* in *repo_path*.

        Returns ``True`` if an existing PR/MR was adopted (caller should skip
        creation), ``False`` otherwise.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(os.path.normpath(repo_path))
        list_cmd = self._list_cmd_args(branch_name)
        logger.debug(
            "Checking for existing %s: %s (cwd=%s)",
            self.entity_name,
            " ".join(list_cmd),
            repo_path,
        )
        try:
            list_result = subprocess.run(
                list_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )
            if list_result.returncode == 0 and list_result.stdout.strip():
                item_list = json.loads(list_result.stdout.strip())
                if item_list:
                    existing_item = item_list[0]
                    item_url, item_number = self._parse_existing_item(existing_item)
                    if item_url:
                        repo_display_name = (
                            extract_repo_from_pull_request_url(item_url) or repo_name
                        )
                        logger.info(
                            "Adopting existing %s for repo %s: %s",
                            self.entity_name,
                            repo_display_name,
                            item_url,
                        )
                        entry = PullRequestEntry(
                            repo=repo_display_name,
                            repo_path=repo_path,
                            url=item_url,
                            number=item_number,
                            adopted=True,
                        )
                        pull_requests.append(entry)
                        context.artifact_store.write_artifact(
                            self.artifact_class(  # type: ignore[call-arg]  # subclass provides artifact_type default
                                workflow_id=context.adw_id,
                                pull_requests=pull_requests,
                                platform=self.platform,
                            )
                        )
                        logger.debug(
                            "Saved %s artifact after adopting %s for %s",
                            self.artifact_slug,
                            self.entity_name,
                            repo_name,
                        )
                        if attachment_md and entry.number:
                            try:
                                self._post_attachment(
                                    repo_path=repo_path,
                                    number=entry.number,
                                    body=attachment_md,
                                    env=env,
                                )
                            except (
                                subprocess.TimeoutExpired,
                                OSError,
                            ) as exc:
                                logger.warning(
                                    "Failed to post attachment comment on %s %s%d: %s",
                                    self.entity_name,
                                    self.entity_prefix,
                                    entry.number,
                                    exc,
                                )
                        return True
        except (
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            TypeError,
            KeyError,
            IndexError,
        ) as e:
            logger.debug(
                "Could not check for existing %s in %s: %s",
                self.entity_name,
                repo_path,
                e,
            )
        return False

    def _process_repo(
        self,
        context: WorkflowContext,
        repo_path: str,
        title: str,
        summary: str,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
    ) -> None:
        """Process a single repository for PR/MR creation.

        Checks for existing PRs/MRs, pushes the branch, and creates a new
        one.  Mutates *pull_requests* in-place when a PR/MR is adopted or
        created.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(os.path.normpath(repo_path))

        # Layer 1: Already done check -- skip if this repo_path is already recorded
        already_done = any(entry.repo_path == repo_path for entry in pull_requests)
        if already_done:
            logger.info(
                "%s for repo %s (%s) already recorded, skipping",
                self.entity_name,
                repo_name,
                repo_path,
            )
            return

        # Determine the current branch name for this repo
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            logger.warning("git rev-parse timed out for %s, skipping branch detection", repo_name)
            branch_name = ""

        # Layer 2: Adopt existing remote PR/MR if one already exists for this branch
        if branch_name and self._try_adopt_existing(
            context, repo_path, branch_name, pull_requests, env, attachment_md
        ):
            return

        # Layer 2.5: Branch-delta guard -- skip creation if no commits ahead of base
        if not has_branch_delta(repo_path, context.adw_id):
            logger.info(
                "No commits ahead of base in %s — skipping %s creation",
                repo_path,
                self.entity_name,
            )
            return

        # Layer 3: Push + create new PR/MR
        push_cmd = ["git", "push", "--set-upstream", "origin", "HEAD"]
        logger.debug("Pushing current branch to origin in %s...", repo_path)
        try:
            push_result = subprocess.run(
                push_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )
            if push_result.returncode == 0:
                logger.debug("Branch pushed successfully for %s", repo_name)
            else:
                logger.debug(
                    "git push failed for %s (exit code %d): %s",
                    repo_name,
                    push_result.returncode,
                    push_result.stderr,
                )
        except subprocess.TimeoutExpired:
            logger.debug(
                "git push timed out for %s, continuing to %s creation",
                repo_name,
                self.entity_name,
            )
        except OSError as e:
            logger.exception("git push failed for %s: %s", repo_name, e)
            raise

        draft = context.pipeline_type == "thin"
        cmd = self._create_cmd_args(title, summary, draft)

        logger.debug("Executing: %s (cwd=%s)", " ".join(cmd), repo_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
                cwd=repo_path,
            )
        except subprocess.TimeoutExpired:
            error_msg = (
                f"{self.cli_binary} {self.entity_name.lower()} create timed out "
                f"for {repo_name} after 120 seconds"
            )
            logger.warning(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": f"{self.output_key_prefix}-failed", "error": error_msg},
            )
            return

        if result.returncode != 0:
            error_msg = (
                f"{self.cli_binary} {self.entity_name.lower()} create failed for {repo_name} "
                f"(exit code {result.returncode}): {result.stderr}"
            )
            logger.warning(
                "%s %s create failed for %s (exit code %d): %s",
                self.cli_binary,
                self.entity_name.lower(),
                repo_name,
                result.returncode,
                result.stderr,
            )
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": f"{self.output_key_prefix}-failed", "error": error_msg},
            )
            # Continue to next repo; partial progress is already saved
            return

        # Parse URL and number from create command output
        parsed = self._parse_create_output(result.stdout)
        if parsed is None:
            logger.error(
                "Could not parse %s URL from %s output for %s: %r",
                self.entity_name,
                self.cli_binary,
                repo_name,
                result.stdout,
            )
            return

        item_url, item_number = parsed
        repo_display_name = extract_repo_from_pull_request_url(item_url) or repo_name
        logger.info("%s created for %s: %s", self.entity_name, repo_display_name, item_url)

        entry = PullRequestEntry(
            repo=repo_display_name,
            repo_path=repo_path,
            url=item_url,
            number=item_number,
            adopted=False,
        )
        pull_requests.append(entry)

        # Write artifact after each repo so partial progress survives failures
        artifact = self.artifact_class(  # type: ignore[call-arg]  # subclass provides artifact_type default
            workflow_id=context.adw_id,
            pull_requests=pull_requests,
            platform=self.platform,
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug(
            "Saved %s artifact after creating %s for %s",
            self.artifact_slug,
            self.entity_name,
            repo_name,
        )

        if attachment_md and entry.number:
            try:
                self._post_attachment(
                    repo_path=repo_path,
                    number=entry.number,
                    body=attachment_md,
                    env=env,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "Failed to post attachment comment on %s %s%d: %s",
                    self.entity_name,
                    self.entity_prefix,
                    entry.number,
                    exc,
                )

    def _seed_pull_requests(self, context: WorkflowContext) -> list[PullRequestEntry]:
        """Load existing pull request entries from the artifact store for rerun continuity.

        Must be called before the preconditions check so that re-runs with no
        uncommitted changes can still adopt existing PRs.

        Args:
            context: Workflow context.

        Returns:
            List of previously written ``PullRequestEntry`` objects, or ``[]``
            if no artifact exists yet.
        """
        logger = get_logger(context.adw_id)
        pull_requests: list[PullRequestEntry] = []
        if context.artifact_store.artifact_exists(self.artifact_slug):
            try:
                existing_artifact = context.artifact_store.read_artifact(
                    self.artifact_slug,
                    self.artifact_class,
                )
                pull_requests = list(existing_artifact.pull_requests)
                logger.debug(
                    "Seeded %d existing %s entries from artifact",
                    len(pull_requests),
                    self.entity_name,
                )
            except (FileNotFoundError, ValueError) as e:
                logger.debug(
                    "Could not load existing %s artifact: %s",
                    self.artifact_slug,
                    e,
                )
        return pull_requests

    def _build_pr_lookup(self, pr_details: list) -> tuple[dict, list]:
        """Build a normalized path-keyed lookup and flat commit list from *pr_details*.

        Args:
            pr_details: The typed list of ``ComposeRequestRepoResult`` instances
                loaded from context.

        Returns:
            A 2-tuple ``(pr_by_repo, all_commits)`` where *pr_by_repo* maps
            ``os.path.realpath(os.path.normpath(repo))`` → repo entry and
            *all_commits* is the flat list of commit entries across all repos
            that have a non-empty ``repo`` attribute.
        """
        pr_by_repo = {
            os.path.realpath(os.path.normpath(r.repo)): r
            for r in pr_details
            if getattr(r, "repo", None)
        }
        all_commits = [
            c for r in pr_details if getattr(r, "repo", None) for c in getattr(r, "commits", [])
        ]
        return pr_by_repo, all_commits

    def _dispatch_repos(
        self,
        context: WorkflowContext,
        affected_repos: list[str],
        pr_by_repo: dict,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
        logger: logging.Logger,
    ) -> bool:
        """Iterate *affected_repos* and dispatch each matched entry to ``_process_repo``.

        Logs a warning for repos with no matching PR-details entry and an info
        message for repos whose matched entry has an empty title.  Distinguishes
        between lookup misses and empty-title skips in the summary message so
        operators can tell which failure mode occurred.

        Args:
            context: Workflow context.
            affected_repos: Repo paths that have active git changes.
            pr_by_repo: Normalized-path-keyed lookup built by ``_build_pr_lookup``.
            pull_requests: Mutable list that ``_process_repo`` appends results to.
            env: Environment dict with the platform token set.
            attachment_md: Rendered attachment Markdown (may be ``None``).
            logger: Logger for the current workflow run.

        Returns:
            ``True`` if at least one repo was dispatched; ``False`` otherwise.
        """
        dispatched_any = False
        lookup_misses = 0
        empty_title_skips = 0

        for repo_path in affected_repos:
            normalized_key = os.path.realpath(os.path.normpath(repo_path))
            repo_pr = pr_by_repo.get(normalized_key)
            if repo_pr is None:
                logger.warning(
                    "No PR details found for repo %s — skipping %s creation",
                    repo_path,
                    self.entity_name,
                )
                lookup_misses += 1
                continue
            title = getattr(repo_pr, "title", "") or ""
            if not title:
                logger.info(
                    "Skipping %s creation for %s: empty title in PR details",
                    self.entity_name,
                    repo_path,
                )
                empty_title_skips += 1
                continue
            dispatched_any = True
            self._process_repo(
                context,
                repo_path,
                title,
                getattr(repo_pr, "summary", "") or "",
                pull_requests,
                env,
                attachment_md,
            )

        if not dispatched_any:
            if empty_title_skips > 0 and lookup_misses == 0:
                skip_msg = (
                    f"{self.entity_name} creation skipped: "
                    f"all matched repo entries had empty titles ({empty_title_skips} skipped)"
                )
            elif lookup_misses > 0 and empty_title_skips == 0:
                skip_msg = (
                    f"{self.entity_name} creation skipped: "
                    "no LLM repo entries matched affected paths"
                )
            else:
                skip_msg = (
                    f"{self.entity_name} creation skipped: "
                    f"no LLM repo entries matched affected paths "
                    f"({lookup_misses} lookup misses, {empty_title_skips} empty-title skips)"
                )
            logger.warning(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": f"{self.output_key_prefix}-skipped", "reason": skip_msg},
            )

        return dispatched_any

    def run(self, context: WorkflowContext) -> StepResult:
        """Create a pull request / merge request using the platform CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Try to load pr_details from artifact if not in context (optional).
        # NOTE: load_optional_artifact caches the result under the "pr_details" key in
        # context.data.  Do not share a WorkflowContext instance across step invocations
        # (e.g. in tests or rerun harnesses) — the cached value will be stale on the
        # second call.  If that becomes necessary, clear context.data["pr_details"] first.
        pr_details = context.load_optional_artifact(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: list(a.repos),
        )

        attachment_md = load_and_render_attachment(context)

        pat_value = os.environ.get(self.pat_env_var, "")

        try:
            # Execute with platform token environment variable
            env = os.environ.copy()
            env[self.token_env_key] = pat_value

            # Layer 0: Seed pull_requests from existing artifact for rerun continuity.
            pull_requests = self._seed_pull_requests(context)

            if result := self._check_preconditions(context, pr_details, logger):
                return result

            # pr_details is guaranteed non-None and non-empty after preconditions pass
            assert pr_details is not None

            pr_by_repo, all_commits = self._build_pr_lookup(pr_details)

            affected_repos = get_affected_repo_paths(context)
            if not affected_repos:
                logger.info("No affected repos — skipping %s creation", self.entity_name)
                # Preserve any seeded entries from a prior run so rerun continuity
                # is not broken when the implement step yields no affected repos.
                artifact = self.artifact_class(  # type: ignore[call-arg]  # subclass provides artifact_type default
                    workflow_id=context.adw_id,
                    pull_requests=pull_requests,
                    platform=self.platform,
                )
                context.artifact_store.write_artifact(artifact)
                return StepResult.ok(None)

            self._dispatch_repos(
                context,
                affected_repos,
                pr_by_repo,
                pull_requests,
                env,
                attachment_md,
                logger,
            )

            # Emit artifact comment and progress comment after all repos are processed
            if pull_requests:
                artifact = self.artifact_class(  # type: ignore[call-arg]  # subclass provides artifact_type default
                    workflow_id=context.adw_id,
                    pull_requests=pull_requests,
                    platform=self.platform,
                )
                status, msg = emit_artifact_comment(
                    context.require_issue_id, context.adw_id, artifact
                )
                log_artifact_comment_status(status, msg)

                urls = [entry.url for entry in pull_requests]
                comment_data = {
                    "commits": all_commits,
                    "output": f"{self.output_key_prefix}-created",
                    "urls": urls,
                }
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    f"{self.entity_name}(s) created: {', '.join(urls)}",
                    comment_data,
                )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = (
                f"{self.cli_binary} {self.entity_name.lower()} create timed out after 120 seconds"
            )
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": f"{self.output_key_prefix}-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = f"{self.cli_binary} CLI not found, skipping {self.entity_name} creation"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": f"{self.output_key_prefix}-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating {self.entity_name.lower()}: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": f"{self.output_key_prefix}-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
