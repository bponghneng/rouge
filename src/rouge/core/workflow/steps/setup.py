"""Setup git environment step implementation.

This step prepares the git environment for a workflow by:
1. Checking out the default branch
2. Resetting to the latest origin state
3. Creating a new feature branch for the workflow

WARNING: This step uses destructive git operations (git reset --hard) which
will discard any uncommitted changes. This is acceptable for worker environments
but requires explicit opt-in via ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS environment
variable in development environments to prevent accidental data loss.
"""

import logging
import os
import subprocess

from rouge.core.database import update_issue_branch
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Default timeout for git operations (60 seconds)
GIT_TIMEOUT = 60


class SetupStep(WorkflowStep):
    """Set up git environment for workflow execution.

    This step prepares the repository by checking out the default branch,
    resetting to origin, and creating a new workflow branch.

    Environment Variables:
        DEFAULT_GIT_BRANCH: The default branch to checkout (defaults to "main")
        REPO_PATH: The repository path (defaults to current directory)
        ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS: Set to "true" to allow destructive git
            operations (git reset --hard). Required for non-worker environments
            to prevent accidental data loss.
    """

    @property
    def name(self) -> str:
        return "Setting up git environment"

    @property
    def is_critical(self) -> bool:
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Execute git setup operations.

        Args:
            context: Workflow context containing adw_id for branch naming

        Returns:
            StepResult with success status and optional error message
        """
        default_branch = os.environ.get("DEFAULT_GIT_BRANCH", "main")
        repo_path = get_repo_path()
        adw_id = context.adw_id

        # Check if destructive git operations are allowed
        allow_destructive = os.environ.get("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "").lower() == "true"

        logger.info(
            "Setting up git environment: default_branch=%s, repo_path=%s, adw_id=%s, "
            "allow_destructive=%s",
            default_branch,
            repo_path,
            adw_id,
            allow_destructive,
        )

        if not allow_destructive:
            error_msg = (
                "Destructive git operations not allowed. "
                "Set ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true to enable git reset --hard. "
                "WARNING: This will discard any uncommitted changes."
            )
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        try:
            # Step 1: Checkout default branch
            checkout_result = subprocess.run(
                ["git", "checkout", default_branch],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=repo_path,
            )
            if checkout_result.returncode != 0:
                error_msg = (
                    f"git checkout {default_branch} failed "
                    f"(exit code {checkout_result.returncode}): {checkout_result.stderr}"
                )
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            logger.debug("Checked out %s branch", default_branch)

            # Step 2: Reset to origin state (destructive operation)
            reset_result = subprocess.run(
                ["git", "reset", "--hard", f"origin/{default_branch}"],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=repo_path,
            )
            if reset_result.returncode != 0:
                error_msg = (
                    f"git reset --hard origin/{default_branch} failed "
                    f"(exit code {reset_result.returncode}): {reset_result.stderr}"
                )
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            logger.debug("Reset to origin/%s", default_branch)

            # Step 3: Create and checkout new workflow branch
            branch_name = f"adw-{adw_id}"
            create_branch_result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT,
                cwd=repo_path,
            )
            if create_branch_result.returncode != 0:
                error_msg = (
                    f"git checkout -b {branch_name} failed "
                    f"(exit code {create_branch_result.returncode}): {create_branch_result.stderr}"
                )
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            logger.debug("Created and checked out branch %s", branch_name)

            # Step 4: Persist branch name to database
            update_issue_branch(context.issue_id, branch_name)
            logger.debug("Persisted branch name %s for issue %s", branch_name, context.issue_id)

            logger.info("Git environment setup complete: branch=%s", branch_name)
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
            error_msg = f"Unexpected error during git setup: {type(e).__name__}: {e}"
            logger.exception("Unexpected error during git setup")
            return StepResult.fail(error_msg)
