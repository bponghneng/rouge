"""Create GitLab merge request step implementation."""

import logging
import os
import subprocess

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_artifact_comment, emit_comment_from_payload
from rouge.core.workflow.artifacts import ComposeRequestArtifact, GlabPullRequestArtifact
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


def _emit_and_log(issue_id: int, adw_id: str, text: str, raw: dict) -> None:
    """Helper to emit comment and log based on status.

    Args:
        issue_id: Issue ID
        adw_id: ADW ID
        text: Comment text
        raw: Raw payload data
    """
    payload = CommentPayload(
        issue_id=issue_id,
        adw_id=adw_id,
        text=text,
        raw=raw,
        source="system",
        kind="workflow",
    )
    status, msg = emit_comment_from_payload(payload)
    if status == "success":
        logger.debug(msg)
    else:
        logger.error(msg)


class GlabPullRequestStep(WorkflowStep):
    """Create GitLab merge request via glab CLI."""

    @property
    def name(self) -> str:
        return "Creating GitLab merge request"

    @property
    def is_critical(self) -> bool:
        # MR creation is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitLab merge request using glab CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load pr_details from artifact if not in context
        pr_details = context.load_artifact_if_missing(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: {"title": a.title, "summary": a.summary, "commits": a.commits},
        )

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
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

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
        gitlab_pat = os.environ.get("GITLAB_PAT")
        if not gitlab_pat:
            skip_msg = "MR creation skipped: GITLAB_PAT environment variable not set"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        try:
            # Execute with GITLAB_TOKEN environment variable (glab uses GITLAB_TOKEN)
            env = os.environ.copy()
            env["GITLAB_TOKEN"] = gitlab_pat

            repo_path = get_repo_path()

            # Push branch to origin before creating MR
            push_cmd = ["git", "push", "--set-upstream", "origin", "HEAD"]
            logger.debug("Pushing current branch to origin...")
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
                    logger.debug("Branch pushed successfully")
                else:
                    logger.debug(
                        "git push failed (exit code %d): %s",
                        push_result.returncode,
                        push_result.stderr,
                    )
            except subprocess.TimeoutExpired:
                logger.debug("git push timed out, continuing to MR creation")
            except Exception as e:
                logger.debug("git push failed: %s", e)

            # Build glab mr create command
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

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
                cwd=repo_path,
            )

            if result.returncode != 0:
                error_msg = (
                    f"glab mr create failed (exit code {result.returncode}): {result.stderr}"
                )
                logger.warning(
                    "glab mr create failed (exit code %d): %s",
                    result.returncode,
                    result.stderr,
                )
                payload = CommentPayload(
                    issue_id=context.require_issue_id,
                    adw_id=context.adw_id,
                    text=error_msg,
                    raw={"output": "merge-request-failed", "error": error_msg},
                    source="system",
                    kind="workflow",
                )
                status, msg = emit_comment_from_payload(payload)
                if status == "success":
                    logger.debug(msg)
                else:
                    logger.error(msg)
                return StepResult.fail(error_msg)

            # Parse MR URL from output (glab mr create outputs the URL)
            mr_url = result.stdout.strip()
            logger.info("Merge request created: %s", mr_url)

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = GlabPullRequestArtifact(
                    workflow_id=context.adw_id,
                    url=mr_url,
                    platform="gitlab",
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved pull_request artifact for workflow %s", context.adw_id)

                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                if status == "success":
                    logger.debug(msg)
                elif status == "skipped":
                    logger.debug(msg)
                else:
                    logger.error(msg)

            # Emit progress comment with MR details
            comment_data = {
                "commits": commits,
                "output": "merge-request-created",
                "url": mr_url,
            }
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=f"Merge request created: {mr_url}",
                raw=comment_data,
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "glab mr create timed out after 120 seconds"
            logger.exception(error_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "glab CLI not found, skipping MR creation"
            logger.exception(error_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating merge request: {e}"
            logger.exception(error_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
