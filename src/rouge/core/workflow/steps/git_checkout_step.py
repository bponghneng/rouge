"""Check out an existing git branch for workflow execution.

This step switches to an already-created feature branch by:
1. Running git checkout <branch>
2. Running git pull --rebase to bring the branch up to date

It is intended for workflows that resume work on an existing branch (e.g.
patch workflows) where the branch already exists in the remote.
"""

import logging
import subprocess

from rouge.core.notifications.comments import emit_artifact_comment, log_artifact_comment_status
from rouge.core.workflow.artifacts import GitCheckoutArtifact
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Default timeout for git operations (60 seconds)
GIT_TIMEOUT = 60


class GitCheckoutStep(WorkflowStep):
    """Check out an existing git branch and pull latest changes.

    This step switches to the branch stored on the issue and rebases it
    against the remote so subsequent steps work on an up-to-date tree.

    Environment Variables:
        REPO_PATH: The repository path (defaults to current directory)
    """

    @property
    def name(self) -> str:
        return "Checking out git branch"

    @property
    def is_critical(self) -> bool:
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Execute git checkout and pull --rebase.

        Args:
            context: Workflow context containing the issue with branch information

        Returns:
            StepResult with success status and optional error message
        """
        # Guard: issue and branch must be set
        if context.issue is None:
            error_msg = "issue is not set in context"
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        branch = context.issue.branch
        if not branch:
            error_msg = "issue.branch is not set"
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        repo_path = get_repo_path()

        logger.info(
            "Checking out git branch: branch=%s, repo_path=%s",
            branch,
            repo_path,
        )

        try:
            # Step 1: Checkout the branch
            checkout_result = subprocess.run(
                ["git", "checkout", branch],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=repo_path,
            )
            if checkout_result.returncode != 0:
                error_msg = (
                    f"git checkout {branch} failed "
                    f"(exit code {checkout_result.returncode}): {checkout_result.stderr}"
                )
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            logger.debug("Checked out branch %s", branch)

            # Step 2: Pull with rebase to bring branch up to date
            pull_result = subprocess.run(
                ["git", "pull", "--rebase", "origin", branch],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=repo_path,
            )
            if pull_result.returncode != 0:
                error_msg = (
                    "git pull --rebase failed "
                    f"(exit code {pull_result.returncode}): {pull_result.stderr}"
                )
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            logger.debug("Pulled latest changes for branch %s", branch)

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = GitCheckoutArtifact(
                    workflow_id=context.adw_id,
                    branch=branch,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved git_checkout artifact for workflow %s", context.adw_id)

                if context.issue_id is not None:
                    status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                    log_artifact_comment_status(status, msg)

            logger.info("Git checkout complete: branch=%s", branch)
            return StepResult.ok(None)

        except subprocess.TimeoutExpired as e:
            error_msg = f"Git operation timed out after {GIT_TIMEOUT} seconds: {e.cmd}"
            logger.error(error_msg)
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "git command not found - ensure git is installed and in PATH"
            logger.error(error_msg)
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during git checkout: {type(e).__name__}: {e}"
            logger.exception("Unexpected error during git checkout")
            return StepResult.fail(error_msg)
