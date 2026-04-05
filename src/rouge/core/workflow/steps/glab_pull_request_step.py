"""Create GitLab merge request step implementation."""

import json
import logging
import os
import re
import subprocess

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
from rouge.core.workflow.shared import get_affected_repo_paths
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import _emit_and_log, load_and_render_attachment
from rouge.core.workflow.types import StepResult

_logger = get_logger(__name__)


def _post_glab_attachment_note(
    repo_path: str,
    mr_number: int,
    body: str,
    env: dict[str, str],
) -> None:
    """Post or update the Rouge review-context note on a GitLab MR."""
    marker = "<!-- rouge-review-context -->"
    tagged_body = f"{marker}\n{body}"

    list_cmd = [
        "glab",
        "api",
        f"projects/:id/merge_requests/{mr_number}/notes?per_page=100",
    ]
    result = subprocess.run(
        list_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
    )

    existing_note_id = None
    if result.returncode == 0 and result.stdout.strip():
        try:
            notes = json.loads(result.stdout)
            for note in notes:
                if note.get("body", "").startswith(marker):
                    existing_note_id = note["id"]
                    break
        except (ValueError, KeyError):
            pass

    if existing_note_id:
        update_cmd = [
            "glab",
            "api",
            "--method",
            "PUT",
            f"projects/:id/merge_requests/{mr_number}/notes/{existing_note_id}",
            "-f",
            f"body={tagged_body}",
        ]
        update_result = subprocess.run(
            update_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if update_result.returncode != 0:
            _logger.warning(
                "Failed to update review-context note on MR !%d: %s",
                mr_number,
                update_result.stderr,
            )
        else:
            _logger.info("Updated review-context note on MR !%d", mr_number)
    else:
        cmd = ["glab", "mr", "note", "create", str(mr_number), "--message", tagged_body]
        create_result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if create_result.returncode != 0:
            _logger.warning(
                "Failed to post review-context note on MR !%d: %s",
                mr_number,
                create_result.stderr,
            )
        else:
            _logger.info("Posted review-context note on MR !%d", mr_number)


class GlabPullRequestStep(WorkflowStep):
    """Create GitLab merge request via glab CLI."""

    @property
    def name(self) -> str:
        return "Creating GitLab merge request"

    @property
    def is_critical(self) -> bool:
        # MR creation is best-effort - workflow continues on failure
        return False

    def _check_preconditions(
        self,
        context: WorkflowContext,
        pr_details: dict | None,
        logger: logging.Logger,
    ) -> StepResult | None:
        """Validate preconditions for MR creation.

        Returns a StepResult if a precondition fails (caller should return it),
        or None if all checks pass.
        """
        if not pr_details:
            skip_msg = "MR creation skipped: no PR details in context"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        title = pr_details.get("title", "")

        if not title:
            skip_msg = "MR creation skipped: MR title is empty"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Check for GITLAB_PAT environment variable
        if not os.environ.get("GITLAB_PAT"):
            skip_msg = "MR creation skipped: GITLAB_PAT environment variable not set"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        return None

    def _try_adopt_existing(
        self,
        context: WorkflowContext,
        repo_path: str,
        branch_name: str,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
    ) -> bool:
        """Check for and adopt an existing GitLab MR for branch_name in repo_path.

        Returns True if an existing MR was adopted (caller should skip Layer 3),
        False otherwise.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(os.path.normpath(repo_path))
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
                        if attachment_md and entry.number:
                            try:
                                _post_glab_attachment_note(
                                    repo_path=repo_path,
                                    mr_number=entry.number,
                                    body=attachment_md,
                                    env=env,
                                )
                            except (
                                subprocess.TimeoutExpired,
                                OSError,
                            ) as exc:
                                logger.warning(
                                    "Failed to post attachment note on MR !%d: %s",
                                    entry.number,
                                    exc,
                                )
                        return True
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.debug("Could not check for existing MR in %s: %s", repo_path, e)
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
        """Process a single repository for MR creation.

        Checks for existing MRs, pushes the branch, and creates a new MR.
        Mutates *pull_requests* in-place when an MR is adopted or created.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(os.path.normpath(repo_path))

        # Layer 1: Already done check — skip if this repo_path is already recorded
        already_done = any(entry.repo_path == repo_path for entry in pull_requests)
        if already_done:
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
        if branch_name and self._try_adopt_existing(
            context, repo_path, branch_name, pull_requests, env, attachment_md
        ):
            return

        # Layer 2.5: Branch-delta guard — skip MR creation if no commits ahead of base
        try:
            base_branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
            base_branch = (
                base_branch_result.stdout.strip().replace("origin/", "")
                if base_branch_result.returncode == 0
                else "main"
            )
            delta_result = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD...origin/{base_branch}"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
            if delta_result.returncode == 0 and delta_result.stdout.strip() == "0":
                logger.info("No commits ahead of base in %s — skipping MR creation", repo_path)
                return
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(
                "Branch-delta check failed for %s: %s, continuing with MR creation",
                repo_path,
                e,
            )

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

        if context.pipeline_type == "thin":
            cmd.append("--draft")

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
            _emit_and_log(
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
            _emit_and_log(
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

        if attachment_md and entry.number:
            try:
                _post_glab_attachment_note(
                    repo_path=repo_path,
                    mr_number=entry.number,
                    body=attachment_md,
                    env=env,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "Failed to post attachment note on MR !%d: %s",
                    entry.number,
                    exc,
                )

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitLab merge request using glab CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Try to load pr_details from artifact if not in context (optional)
        pr_details = context.load_optional_artifact(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: {"title": a.title, "summary": a.summary, "commits": a.commits},
        )

        attachment_md = load_and_render_attachment(context)

        if result := self._check_preconditions(context, pr_details, logger):
            return result

        # pr_details is guaranteed non-None after preconditions pass
        assert pr_details is not None
        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])
        gitlab_pat = os.environ.get("GITLAB_PAT", "")

        try:
            # Execute with GITLAB_TOKEN environment variable (glab uses GITLAB_TOKEN)
            env = os.environ.copy()
            env["GITLAB_TOKEN"] = gitlab_pat

            # Seed pull_requests from existing artifact for rerun continuity (Layer 0)
            pull_requests: list[PullRequestEntry] = []
            if context.artifact_store.artifact_exists("glab-pull-request"):
                try:
                    existing_artifact = context.artifact_store.read_artifact(
                        "glab-pull-request", GlabPullRequestArtifact
                    )
                    pull_requests = list(existing_artifact.pull_requests)
                    logger.debug("Seeded %d existing MR entries from artifact", len(pull_requests))
                except Exception as e:
                    logger.debug("Could not load existing glab-pull-request artifact: %s", e)

            affected_repos = get_affected_repo_paths(context)
            if not affected_repos:
                logger.info("No affected repos — skipping MR creation")
                artifact = GlabPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=[],
                    platform="gitlab",
                )
                context.artifact_store.write_artifact(artifact)
                return StepResult.ok(None)

            for repo_path in affected_repos:
                self._process_repo(
                    context, repo_path, title, summary, pull_requests, env, attachment_md
                )

            # Emit artifact comment and progress comment after all repos are processed
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
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    f"Merge request(s) created: {', '.join(mr_urls)}",
                    comment_data,
                )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "glab mr create timed out after 120 seconds"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "glab CLI not found, skipping MR creation"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating merge request: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
