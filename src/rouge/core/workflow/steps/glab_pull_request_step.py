"""Create GitLab merge request step implementation."""

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Optional

from rouge.core.notifications.comments import (
    emit_artifact_comment,
    log_artifact_comment_status,
)
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ComposeRequestArtifact,
    GlabPullRequestArtifact,
    PullRequestEntry,
)
from rouge.core.workflow.repo_filter import get_affected_repos
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import emit_and_log, has_commits_ahead_of_base
from rouge.core.workflow.types import StepResult


class GlabPullRequestStep(WorkflowStep):
    """Create GitLab merge request via glab CLI."""

    @property
    def name(self) -> str:
        return "Creating GitLab merge request"

    @property
    def is_critical(self) -> bool:
        # MR creation is best-effort - workflow continues on failure
        return False

    def _validate_prerequisites(
        self, context: WorkflowContext, logger: logging.Logger
    ) -> tuple[Optional[dict], Optional[StepResult]]:
        """Validate all prerequisites for MR creation.

        Args:
            context: Workflow context
            logger: Logger instance

        Returns:
            Tuple of (pr_details, early_return). If early_return is not None,
            the caller should return it immediately. Otherwise pr_details is valid.
        """

        def _skip(msg: str) -> StepResult:
            logger.info(msg)
            emit_and_log(
                context.require_issue_id,
                context.adw_id,
                msg,
                {"output": "merge-request-skipped", "reason": msg},
            )
            return StepResult.ok(None)

        pr_details = context.load_optional_artifact(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: {"title": a.title, "summary": a.summary, "commits": a.commits},
        )

        if not pr_details:
            return None, _skip("MR creation skipped: no PR details in context")

        if not pr_details.get("title", ""):
            return None, _skip("MR creation skipped: MR title is empty")

        if not os.environ.get("GITLAB_PAT"):
            return None, _skip("MR creation skipped: GITLAB_PAT environment variable not set")

        if not shutil.which("glab"):
            logger.debug("Current PATH: %s", os.environ.get("PATH", ""))
            return None, _skip("MR creation skipped: glab CLI not found in PATH")

        return pr_details, None

    def _process_repo(
        self,
        repo_path: str,
        title: str,
        summary: str,
        env: dict,
        pull_requests: list[PullRequestEntry],
        context: WorkflowContext,
        logger: logging.Logger,
    ) -> None:
        """Process a single repository: adopt existing MR or push and create a new one.

        Modifies pull_requests in place and persists the artifact incrementally.

        Args:
            repo_path: Absolute path to the repository.
            title: MR title.
            summary: MR body / summary.
            env: Environment dict with GITLAB_TOKEN set.
            pull_requests: Running list of MR entries (mutated in place).
            context: Workflow context.
            logger: Logger instance.
        """
        repo_name = os.path.basename(os.path.normpath(repo_path))

        # Layer 1: Already done check — skip if this repo_path is already recorded
        if any(entry.repo_path == repo_path for entry in pull_requests):
            logger.info(
                "MR for repo %s (%s) already recorded, skipping",
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

        # Layer 2: Adopt existing remote MR if one already exists for this branch
        if branch_name:
            list_cmd = [
                "glab",
                "mr",
                "list",
                "--source-branch",
                branch_name,
                "--output",
                "json",
            ]
            logger.debug("Checking for existing MR: %s (cwd=%s)", " ".join(list_cmd), repo_path)
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
                    mr_list = json.loads(list_result.stdout.strip())
                    if mr_list:
                        existing_mr = mr_list[0]
                        mr_url = existing_mr.get("web_url", "")
                        mr_number = existing_mr.get("iid")
                        if mr_url:
                            logger.info(
                                "Adopting existing MR for repo %s: %s",
                                repo_name,
                                mr_url,
                            )
                            entry = PullRequestEntry(
                                repo=repo_name,
                                repo_path=repo_path,
                                url=mr_url,
                                number=mr_number,
                                adopted=True,
                            )
                            pull_requests.append(entry)
                            context.artifact_store.write_artifact(
                                GlabPullRequestArtifact(
                                    workflow_id=context.adw_id,
                                    pull_requests=pull_requests,
                                    platform="gitlab",
                                )
                            )
                            logger.debug(
                                "Saved glab-pull-request artifact after adopting MR for %s",
                                repo_name,
                            )
                            return
            except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                logger.debug("Could not check for existing MR in %s: %s", repo_path, e)

        # Check if branch has meaningful delta vs base
        if not has_commits_ahead_of_base(repo_path, logger):
            logger.info(
                "Skipping PR/MR creation for %s: no commits ahead of base",
                repo_name,
            )
            return

        # Layer 3: Push + create new MR
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
            logger.debug("git push timed out for %s, continuing to MR creation", repo_name)
        except OSError as e:
            logger.exception("git push failed for %s: %s", repo_name, e)
            raise

        cmd = [
            "glab",
            "mr",
            "create",
            "--title",
            title,
            "--description",
            summary,
        ]

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
            error_msg = f"glab mr create timed out for {repo_name} after 120 seconds"
            logger.warning(error_msg)
            emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return

        if result.returncode != 0:
            error_msg = (
                f"glab mr create failed for {repo_name} "
                f"(exit code {result.returncode}): {result.stderr}"
            )
            logger.warning(
                "glab mr create failed for %s (exit code %d): %s",
                repo_name,
                result.returncode,
                result.stderr,
            )
            emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            # Continue to next repo; partial progress is already saved
            return

        # Parse MR URL from output (glab mr create outputs the URL)
        url_match = re.search(r"https?://\S+/merge_requests/\d+", result.stdout)
        if not url_match:
            logger.error(
                "Could not parse MR URL from glab output for %s: %r",
                repo_name,
                result.stdout,
            )
            return
        mr_url = url_match.group(0)
        logger.info("Merge request created for %s: %s", repo_name, mr_url)

        # Extract MR number from URL
        mr_number = None
        number_match = re.search(r"/merge_requests/(\d+)", mr_url)
        if number_match:
            mr_number = int(number_match.group(1))

        entry = PullRequestEntry(
            repo=repo_name,
            repo_path=repo_path,
            url=mr_url,
            number=mr_number,
            adopted=False,
        )
        pull_requests.append(entry)

        # Write artifact after each repo so partial progress survives failures
        artifact = GlabPullRequestArtifact(
            workflow_id=context.adw_id,
            pull_requests=pull_requests,
            platform="gitlab",
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved glab-pull-request artifact after creating MR for %s", repo_name)

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitLab merge request using glab CLI.

        Validates prerequisites, loads artifacts, iterates affected repos,
        persists progress, and emits a summary comment.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Validate — returns early if any prerequisite is missing
        pr_details, early_return = self._validate_prerequisites(context, logger)
        if early_return is not None:
            return early_return

        assert pr_details is not None  # guaranteed by _validate_prerequisites
        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        try:
            # Execute with GITLAB_TOKEN environment variable (glab uses GITLAB_TOKEN)
            env = os.environ.copy()
            env["GITLAB_TOKEN"] = os.environ["GITLAB_PAT"]

            # Seed pull_requests from existing artifact for rerun continuity (Layer 0)
            pull_requests: list[PullRequestEntry] = []
            if context.artifact_store.artifact_exists("glab-pull-request"):
                try:
                    existing_artifact = context.artifact_store.read_artifact(
                        "glab-pull-request", GlabPullRequestArtifact
                    )
                    pull_requests = list(existing_artifact.pull_requests)
                    logger.debug("Seeded %d existing MR entries from artifact", len(pull_requests))
                except (FileNotFoundError, ValueError) as e:
                    logger.debug("Could not load existing glab-pull-request artifact: %s", e)

            # Use affected_repos from implement artifact; skip MR creation when empty
            # (empty means implementation touched no repos — no fallback to all repos)
            affected_repos, _implement_data = get_affected_repos(context)
            target_repos = affected_repos

            # Iterate — delegate per-repo work to _process_repo
            for repo_path in target_repos:
                self._process_repo(repo_path, title, summary, env, pull_requests, context, logger)

            # Persist final artifact and emit summary comment
            if pull_requests:
                artifact = GlabPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=pull_requests,
                    platform="gitlab",
                )
                status, msg = emit_artifact_comment(
                    context.require_issue_id, context.adw_id, artifact
                )
                log_artifact_comment_status(status, msg)

                mr_urls = [entry.url for entry in pull_requests]
                comment_data = {
                    "commits": commits,
                    "output": "merge-request-created",
                    "urls": mr_urls,
                }
                emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    f"Merge request(s) created: {', '.join(mr_urls)}",
                    comment_data,
                )

            return StepResult.ok(None)

        except FileNotFoundError:
            error_msg = "glab CLI not found, skipping MR creation"
            logger.exception(error_msg)
            emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating merge request: {e}"
            logger.exception(error_msg)
            emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
