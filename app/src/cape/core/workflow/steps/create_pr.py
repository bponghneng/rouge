"""Create pull request step implementation."""

import os
import subprocess

from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import StepResult
from cape.core.workflow.workflow_io import emit_progress_comment


class CreatePullRequestStep(WorkflowStep):
    """Create GitHub pull request via gh CLI."""

    @property
    def name(self) -> str:
        return "Creating pull request"

    @property
    def is_critical(self) -> bool:
        # PR creation is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitHub pull request using gh CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = context.logger

        # Check for pr_details in context
        pr_details = context.data.get("pr_details")
        if not pr_details:
            logger.warning("No PR details found in context, skipping PR creation")
            return StepResult.fail("No PR details found in context, skipping PR creation")

        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        if not title:
            logger.warning("PR title is empty, skipping PR creation")
            return StepResult.fail("PR title is empty, skipping PR creation")

        # Check for GITHUB_PAT environment variable
        github_pat = os.environ.get("GITHUB_PAT")
        if not github_pat:
            logger.warning("GITHUB_PAT environment variable not set, skipping PR creation")
            return StepResult.fail("GITHUB_PAT environment variable not set, skipping PR creation")

        try:
            # Build gh pr create command
            cmd = [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                summary,
            ]

            # Execute with GH_TOKEN environment variable
            env = os.environ.copy()
            env["GH_TOKEN"] = github_pat

            logger.debug("Executing: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )

            if result.returncode != 0:
                logger.warning(
                    "gh pr create failed (exit code %d): %s",
                    result.returncode,
                    result.stderr,
                )
                return StepResult.fail(
                    f"gh pr create failed (exit code {result.returncode}): {result.stderr}"
                )

            # Parse PR URL from output (gh pr create outputs the URL)
            pr_url = result.stdout.strip()
            logger.info("Pull request created: %s", pr_url)

            # Emit progress comment with PR details
            comment_data = {
                "commits": commits,
                "output": "pull-request-created",
                "url": pr_url,
            }
            emit_progress_comment(
                context.issue_id,
                f"Pull request created: {pr_url}",
                logger,
                raw=comment_data,
            )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            logger.warning("gh pr create timed out after 120 seconds")
            return StepResult.fail("gh pr create timed out after 120 seconds")
        except FileNotFoundError:
            logger.warning("gh CLI not found, skipping PR creation")
            return StepResult.fail("gh CLI not found, skipping PR creation")
        except Exception as e:
            logger.warning(f"Error creating pull request: {e}")
            return StepResult.fail(f"Error creating pull request: {e}")
