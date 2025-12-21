"""Create GitLab merge request step implementation."""

import logging
import os
import subprocess

from rouge.core.workflow.artifacts import PRMetadataArtifact, PullRequestArtifact
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class CreateGitLabPullRequestStep(WorkflowStep):
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
        # Check for pr_details in context
        pr_details = context.data.get("pr_details")

        # Try to load from artifact if not in context
        if not pr_details and context.artifacts_enabled and context.artifact_store is not None:
            try:
                pr_meta_artifact = context.artifact_store.read_artifact(
                    "pr_metadata", PRMetadataArtifact
                )
                pr_details = {
                    "title": pr_meta_artifact.title,
                    "summary": pr_meta_artifact.summary,
                    "commits": pr_meta_artifact.commits,
                }
                context.data["pr_details"] = pr_details
                logger.debug("Loaded pr_metadata from artifact")
            except FileNotFoundError:
                # Artifact is optional; if it's missing we simply proceed without MR metadata.
                logger.debug("No pr_metadata artifact found; proceeding without it")

        if not pr_details:
            skip_msg = "MR creation skipped: no PR details in context"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        if not title:
            skip_msg = "MR creation skipped: MR title is empty"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "merge-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Check for GITLAB_PAT environment variable
        gitlab_pat = os.environ.get("GITLAB_PAT")
        if not gitlab_pat:
            skip_msg = "MR creation skipped: GITLAB_PAT environment variable not set"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "merge-request-skipped", "reason": skip_msg},
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
                emit_progress_comment(
                    context.issue_id,
                    error_msg,
                    raw={"output": "merge-request-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            # Parse MR URL from output (glab mr create outputs the URL)
            mr_url = result.stdout.strip()
            logger.info("Merge request created: %s", mr_url)

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = PullRequestArtifact(
                    workflow_id=context.adw_id,
                    url=mr_url,
                    platform="gitlab",
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved pull_request artifact for workflow %s", context.adw_id)

            # Emit progress comment with MR details
            comment_data = {
                "commits": commits,
                "output": "merge-request-created",
                "url": mr_url,
            }
            emit_progress_comment(
                context.issue_id,
                f"Merge request created: {mr_url}",
                raw=comment_data,
            )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "glab mr create timed out after 120 seconds"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "glab CLI not found, skipping MR creation"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating merge request: {e}"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
