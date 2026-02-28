"""Set up git branch for workflow execution.

This step prepares the git environment for a workflow by:
1. Checking out the default branch (with fallback to git checkout -t origin/<branch>
   if local branch is missing)
2. Fetching the latest remote state from all remotes with git fetch --all --prune
3. Resetting to the latest origin state with git reset --hard
4. Deleting any existing workflow branch (if present) with git branch -D
5. Creating a new feature branch for the workflow

Standardized Error Messages:
- ERROR_MISSING_DEFAULT_BRANCH: Default branch not found locally or on remote
- ERROR_CHECKOUT_FAILED: Failed to checkout default branch
- ERROR_FETCH_FAILED: git fetch --all --prune failed
- ERROR_RESET_FAILED: git reset --hard failed
- ERROR_INVALID_BRANCH_NAME: Invalid branch name (whitespace-only)
- ERROR_DELETE_BRANCH_FAILED: Failed to delete existing branch
- ERROR_CREATE_BRANCH_FAILED: Failed to create branch
- ERROR_TIMEOUT: Git operation timed out
- ERROR_GIT_NOT_FOUND: git command not found

WARNING: This step uses destructive git operations (git reset --hard, git branch -D)
which will discard any uncommitted changes and delete existing branches. This is
acceptable for worker environments but requires explicit opt-in via
ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS environment variable in development environments
to prevent accidental data loss.
"""

import logging
import os
import subprocess

from rouge.core.database import update_issue
from rouge.core.notifications.comments import emit_artifact_comment, log_artifact_comment_status
from rouge.core.workflow.artifacts import GitBranchArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Default timeout for git operations (60 seconds)
GIT_TIMEOUT = 60

# Standardized error message templates
ERROR_MISSING_DEFAULT_BRANCH = "Default branch '{default_branch}' not found locally or on remote."
ERROR_CHECKOUT_FAILED = "Failed to checkout default branch '{default_branch}'"
ERROR_FETCH_FAILED = "git fetch --all --prune failed"
ERROR_RESET_FAILED = "git reset --hard failed"
ERROR_INVALID_BRANCH_NAME = "Invalid branch name: issue.branch is whitespace-only"
ERROR_DELETE_BRANCH_FAILED = "Failed to delete existing branch '{branch}'"
ERROR_CREATE_BRANCH_FAILED = "Failed to create branch '{branch}'"
ERROR_TIMEOUT = "Git operation timed out after {timeout} seconds."
ERROR_GIT_NOT_FOUND = "git command not found - ensure git is installed and in PATH"


class GitBranchStep(WorkflowStep):
    """Set up git branch for workflow execution.

    This step prepares the repository by checking out the default branch,
    resetting to origin, and creating a new workflow branch.

    If the local default branch is missing, automatically falls back to checking
    out from the remote with tracking (git checkout -t origin/<branch>).

    Environment Variables:
        DEFAULT_GIT_BRANCH: The default branch to checkout (defaults to "main")
        REPO_PATH: The repository path (defaults to current directory)
        ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS: Set to "true" to allow destructive git
            operations (git reset --hard, git branch -D). Required for non-worker
            environments to prevent accidental data loss.

    Error Messages:
        Uses standardized error message templates defined as module constants
        (ERROR_MISSING_DEFAULT_BRANCH, ERROR_CHECKOUT_FAILED, ERROR_FETCH_FAILED,
        ERROR_RESET_FAILED, ERROR_INVALID_BRANCH_NAME, ERROR_DELETE_BRANCH_FAILED,
        ERROR_CREATE_BRANCH_FAILED, ERROR_TIMEOUT, ERROR_GIT_NOT_FOUND).
    """

    @property
    def name(self) -> str:
        return "Setting up git environment"

    @property
    def is_critical(self) -> bool:
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Execute git branch setup operations.

        Args:
            context: Workflow context containing issue and adw_id for branch naming

        Returns:
            StepResult with success status and optional error message
        """
        default_branch = os.environ.get("DEFAULT_GIT_BRANCH", "main")
        adw_id = context.adw_id

        # Check if destructive git operations are allowed
        allow_destructive = os.environ.get("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "").lower() == "true"

        logger.info(
            "Setting up git environment: default_branch=%s, repo_paths=%s, adw_id=%s, "
            "allow_destructive=%s",
            default_branch,
            context.repo_paths,
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

        # Determine branch name once — all repos share the same branch
        if context.issue and context.issue.branch:
            branch_candidate = context.issue.branch.strip()
            if not branch_candidate:
                error_msg = ERROR_INVALID_BRANCH_NAME
                logger.error(error_msg)
                return StepResult.fail(error_msg)
            branch_name = branch_candidate
        else:
            branch_name = f"adw-{context.adw_id}"

        try:
            for repo_path in context.repo_paths:
                logger.info("Processing repo: %s", repo_path)

                # Step 1: Checkout default branch
                checkout_result = subprocess.run(
                    ["git", "checkout", default_branch],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if checkout_result.returncode != 0:
                    # Log detailed diagnostics at DEBUG level
                    logger.debug(
                        "git checkout %s failed: exit_code=%d, stderr=%s",
                        default_branch,
                        checkout_result.returncode,
                        checkout_result.stderr.strip(),
                    )

                    # Check if failure is due to missing local branch
                    stderr = checkout_result.stderr.lower()
                    if "pathspec" in stderr and "did not match" in stderr:
                        logger.debug("Local default branch not found, trying remote fallback")
                        # Attempt to checkout from remote with tracking
                        fallback_result = subprocess.run(
                            ["git", "checkout", "-t", f"origin/{default_branch}"],
                            capture_output=True,
                            text=True,
                            timeout=GIT_TIMEOUT,
                            cwd=repo_path,
                        )
                        if fallback_result.returncode != 0:
                            logger.debug(
                                "Remote fallback failed: exit_code=%d, stderr=%s",
                                fallback_result.returncode,
                                fallback_result.stderr.strip(),
                            )
                            error_msg = ERROR_MISSING_DEFAULT_BRANCH.format(
                                default_branch=default_branch
                            )
                            logger.error(error_msg)
                            return StepResult.fail(error_msg)
                        logger.debug("Checked out default branch %s from remote", default_branch)
                    else:
                        # Other checkout failure - fail fast without fallback
                        error_msg = ERROR_CHECKOUT_FAILED.format(default_branch=default_branch)
                        logger.error(error_msg)
                        return StepResult.fail(error_msg)
                else:
                    logger.debug("Checked out %s branch", default_branch)

                # Step 2: Fetch latest remote state from all remotes and prune deleted refs
                fetch_result = subprocess.run(
                    ["git", "fetch", "--all", "--prune"],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if fetch_result.returncode != 0:
                    logger.debug(
                        "git fetch --all --prune failed: exit_code=%d, stderr=%s",
                        fetch_result.returncode,
                        fetch_result.stderr.strip(),
                    )
                    error_msg = ERROR_FETCH_FAILED
                    logger.error(error_msg)
                    return StepResult.fail(error_msg)
                logger.debug("Fetched latest remote state from all remotes")

                # Step 3: Reset to origin state (destructive operation)
                reset_result = subprocess.run(
                    ["git", "reset", "--hard", f"origin/{default_branch}"],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if reset_result.returncode != 0:
                    logger.debug(
                        "git reset --hard origin/%s failed: exit_code=%d, stderr=%s",
                        default_branch,
                        reset_result.returncode,
                        reset_result.stderr.strip(),
                    )
                    error_msg = ERROR_RESET_FAILED
                    logger.error(error_msg)
                    return StepResult.fail(error_msg)
                logger.debug("Reset to origin/%s", default_branch)

                # Step 4: Create and checkout new workflow branch

                # Check if local branch already exists
                check_branch_result = subprocess.run(
                    ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if check_branch_result.returncode == 0:
                    # Branch exists locally - delete it to ensure fresh creation
                    logger.debug(
                        "Local branch %s exists, deleting to ensure fresh creation",
                        branch_name,
                    )
                    delete_branch_result = subprocess.run(
                        ["git", "branch", "-D", branch_name],
                        capture_output=True,
                        text=True,
                        timeout=GIT_TIMEOUT,
                        cwd=repo_path,
                    )
                    if delete_branch_result.returncode != 0:
                        logger.debug(
                            "git branch -D %s failed: exit_code=%d, stderr=%s",
                            branch_name,
                            delete_branch_result.returncode,
                            delete_branch_result.stderr.strip(),
                        )
                        error_msg = ERROR_DELETE_BRANCH_FAILED.format(branch=branch_name)
                        logger.error(error_msg)
                        return StepResult.fail(error_msg)
                    logger.debug("Deleted existing branch %s", branch_name)
                else:
                    logger.debug("Local branch %s does not exist, will create fresh", branch_name)

                # Create and checkout new workflow branch
                create_branch_result = subprocess.run(
                    ["git", "checkout", "-b", branch_name],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if create_branch_result.returncode != 0:
                    logger.debug(
                        "git checkout -b %s failed: exit_code=%d, stderr=%s",
                        branch_name,
                        create_branch_result.returncode,
                        create_branch_result.stderr.strip(),
                    )
                    error_msg = ERROR_CREATE_BRANCH_FAILED.format(branch=branch_name)
                    logger.error(error_msg)
                    return StepResult.fail(error_msg)
                logger.debug("Created and checked out branch %s in repo %s", branch_name, repo_path)

            # Step 5: Persist branch name to database (once, after all repos succeed)
            update_issue(context.require_issue_id, branch=branch_name)
            logger.debug(
                "Persisted branch name %s for issue %s", branch_name, context.require_issue_id
            )

            # Save artifact to the artifact store
            artifact = GitBranchArtifact(
                workflow_id=context.adw_id,
                branch=branch_name,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved git_branch artifact for workflow %s", context.adw_id)

            if context.issue_id is not None:
                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                log_artifact_comment_status(status, msg)

            logger.info("Git environment setup complete: branch=%s", branch_name)
            return StepResult.ok(None)

        except subprocess.TimeoutExpired as e:
            logger.debug("Git operation timed out: cmd=%s, timeout=%d", e.cmd, GIT_TIMEOUT)
            error_msg = ERROR_TIMEOUT.format(timeout=GIT_TIMEOUT)
            logger.error(error_msg)
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = ERROR_GIT_NOT_FOUND
            logger.error(error_msg)
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during git setup: {type(e).__name__}: {e}"
            logger.exception("Unexpected error during git setup")
            return StepResult.fail(error_msg)
