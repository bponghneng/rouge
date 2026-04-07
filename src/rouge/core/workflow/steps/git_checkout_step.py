"""Check out an existing git branch for workflow execution.

This step switches to an already-created feature branch by:
1. (Optional) Running git reset --hard and git clean -fd to clean dirty state
   (only if ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true)
2. Running git fetch --all --prune to update remote refs
3. Running git checkout <branch> (with fallback to git checkout -t origin/<branch>
   if local branch is missing)
4. Running git pull --rebase to bring the branch up to date

It is intended for workflows that resume work on an existing branch (e.g.
patch workflows) where the branch already exists in the remote.

This step is source-agnostic: it resolves the issue (and therefore the branch)
from whichever source is available, in the following priority order:
1. ``context.issue`` — set directly on the context (e.g. by a preceding
   FetchIssueStep or supplied by the caller).
2. ``FetchPatchArtifact`` — the patch pipeline artifact written by a preceding
   fetch-patch step.

This keeps full backward compatibility with the patch pipeline while allowing
other pipelines to supply the issue via ``context.issue`` without needing a
FetchPatchArtifact on disk.

Standardized Error Messages:
- ERROR_MISSING_BRANCH: Branch not found locally or on remote
- ERROR_DIRTY_TREE: Working tree has uncommitted changes (requires destructive ops)
- ERROR_PULL_REBASE_CONFLICT: Pull-rebase failed with conflicts
- ERROR_TIMEOUT: Git operation timed out
- ERROR_GIT_NOT_FOUND: git command not found

WARNING: This step may use destructive git operations (git reset --hard and
git clean -fd) to clean the working tree before checkout. This requires
explicit opt-in via ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS environment variable
in development environments to prevent accidental data loss.
"""

import os
import subprocess
from typing import cast

from rouge.core.models import Issue
from rouge.core.utils import get_logger
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

# Default timeout for git operations (60 seconds)
GIT_TIMEOUT = 60

# Standardized error message templates
ERROR_MISSING_BRANCH = "Branch '{branch}' not found locally or on remote."
ERROR_DIRTY_TREE = (
    "Cannot checkout branch: working tree has uncommitted changes. "
    "Set ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true to allow cleanup."
)
ERROR_PULL_REBASE_CONFLICT = "Pull-rebase failed with conflicts."
ERROR_TIMEOUT = "Git operation timed out after {timeout} seconds."
ERROR_GIT_NOT_FOUND = "git command not found - ensure git is installed and in PATH"


class GitCheckoutStep(WorkflowStep):
    """Check out an existing git branch and pull latest changes.

    This step is source-agnostic: it resolves the issue (and therefore the
    branch) from ``context.issue`` when available, and falls back to loading
    it from a ``FetchPatchArtifact`` otherwise.  This makes the step usable
    in both the patch pipeline (artifact-based) and in pipelines that supply
    the issue directly on the context.

    If the local branch is missing, automatically falls back to checking out
    from the remote with tracking (git checkout -t origin/<branch>).

    Environment Variables:
        ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS: Set to "true" to allow destructive git
            operations (git reset --hard, git clean -fd) for cleaning dirty
            working trees. Required for non-worker environments to prevent
            accidental data loss.

    Error Messages:
        Uses standardized error message templates defined as module constants
        (ERROR_MISSING_BRANCH, ERROR_DIRTY_TREE, ERROR_PULL_REBASE_CONFLICT,
        ERROR_TIMEOUT, ERROR_GIT_NOT_FOUND).
    """

    @property
    def name(self) -> str:
        return "Checking out git branch"

    @property
    def is_critical(self) -> bool:
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Execute git checkout and pull --rebase.

        Resolves the issue from the first available source:
        1. ``context.issue`` — supplied directly by the caller or a preceding step.
        2. ``FetchPatchArtifact`` — patch pipeline artifact (backward-compatible path).

        Args:
            context: Workflow context containing the issue with branch information

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Prefer context.issue when available (source-agnostic path).
        if context.issue is not None:
            issue = context.issue
        else:
            # Fall back to loading from context data (patch pipeline).
            try:
                fetch_patch_data = context.load_required_artifact("fetch-patch")
                raw_issue = (
                    fetch_patch_data.get("patch") if isinstance(fetch_patch_data, dict) else None
                )
                if raw_issue is None:
                    raise StepInputError("fetch-patch data does not contain patch issue")
                issue = cast(Issue, raw_issue)
            except StepInputError as e:
                error_msg = str(e)
                logger.error(error_msg)
                return StepResult.fail(error_msg)

        branch = issue.branch
        if not branch:
            error_msg = "issue.branch is not set"
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        # Check if destructive git operations are allowed
        allow_destructive = os.environ.get("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "").lower() == "true"

        logger.info(
            "Checking out git branch: branch=%s, repo_paths=%s, allow_destructive=%s",
            branch,
            context.repo_paths,
            allow_destructive,
        )

        if not context.repo_paths:
            error_msg = "No repo_paths provided; cannot checkout branch"
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        try:
            checked_out_repos: list[str] = []
            for repo_path in context.repo_paths:
                logger.info("Processing repo: %s", repo_path)

                # Step 0: Clean dirty state if allowed (before attempting checkout)
                if allow_destructive:
                    # Reset any uncommitted changes
                    reset_result = subprocess.run(
                        ["git", "reset", "--hard"],
                        capture_output=True,
                        text=True,
                        timeout=GIT_TIMEOUT,
                        cwd=repo_path,
                    )
                    if reset_result.returncode != 0:
                        logger.debug(
                            "git reset --hard failed: exit_code=%d, stderr=%s",
                            reset_result.returncode,
                            reset_result.stderr.strip(),
                        )
                        error_msg = f"git reset --hard failed (exit code {reset_result.returncode})"
                        logger.error(error_msg)
                        return StepResult.fail(error_msg)
                    logger.debug("Reset uncommitted changes")

                    # Remove untracked files
                    clean_result = subprocess.run(
                        ["git", "clean", "-fd"],
                        capture_output=True,
                        text=True,
                        timeout=GIT_TIMEOUT,
                        cwd=repo_path,
                    )
                    if clean_result.returncode != 0:
                        logger.debug(
                            "git clean -fd failed: exit_code=%d, stderr=%s",
                            clean_result.returncode,
                            clean_result.stderr.strip(),
                        )
                        error_msg = f"git clean -fd failed (exit code {clean_result.returncode})"
                        logger.error(error_msg)
                        return StepResult.fail(error_msg)
                    logger.debug("Cleaned untracked files")

                # Step 1: Fetch all remote refs and prune deleted branches
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
                    error_msg = (
                        f"git fetch --all --prune failed (exit code {fetch_result.returncode})"
                    )
                    logger.error(error_msg)
                    return StepResult.fail(error_msg)
                logger.debug("Fetched latest remote refs")

                # Step 2: Checkout the branch
                checkout_result = subprocess.run(
                    ["git", "checkout", branch],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if checkout_result.returncode != 0:
                    # Log detailed diagnostics at DEBUG level
                    logger.debug(
                        "git checkout failed: exit_code=%d, stderr=%s",
                        checkout_result.returncode,
                        checkout_result.stderr.strip(),
                    )

                    # Check if failure is due to dirty working tree
                    stderr = checkout_result.stderr.lower()
                    if "uncommitted changes" in stderr or "would be overwritten" in stderr:
                        if not allow_destructive:
                            error_msg = ERROR_DIRTY_TREE
                            logger.error(error_msg)
                            return StepResult.fail(error_msg)

                    # Check if failure is due to missing local branch
                    if "pathspec" in stderr and "did not match" in stderr:
                        logger.debug("Local branch not found, trying remote fallback")
                        # Attempt to checkout from remote with tracking
                        fallback_result = subprocess.run(
                            ["git", "checkout", "-t", f"origin/{branch}"],
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
                            logger.warning(
                                "Branch '%s' not found in repo %s, skipping",
                                branch,
                                repo_path,
                            )
                            continue
                        logger.debug("Checked out branch %s from remote", branch)
                    else:
                        # Other checkout failure - fail fast without fallback
                        error_msg = f"Failed to checkout branch '{branch}'"
                        logger.error(error_msg)
                        return StepResult.fail(error_msg)
                else:
                    logger.debug("Checked out branch %s", branch)

                # Step 3: Pull with rebase to bring branch up to date
                pull_result = subprocess.run(
                    ["git", "pull", "--rebase", "origin", branch],
                    capture_output=True,
                    text=True,
                    timeout=GIT_TIMEOUT,
                    cwd=repo_path,
                )
                if pull_result.returncode != 0:
                    logger.debug(
                        "git pull --rebase failed: exit_code=%d, stderr=%s",
                        pull_result.returncode,
                        pull_result.stderr.strip(),
                    )
                    # Check if failure is due to rebase conflict
                    stderr = pull_result.stderr.lower()
                    if "conflict" in stderr or "rebase" in stderr:
                        error_msg = ERROR_PULL_REBASE_CONFLICT
                    else:
                        error_msg = f"git pull --rebase failed (exit code {pull_result.returncode})"
                    logger.error(error_msg)
                    return StepResult.fail(error_msg)
                logger.debug("Pulled latest changes for branch %s in repo %s", branch, repo_path)
                checked_out_repos.append(repo_path)

            # Fail if the branch was not found in any repo
            if not checked_out_repos:
                error_msg = ERROR_MISSING_BRANCH.format(branch=branch)
                logger.error(error_msg)
                return StepResult.fail(error_msg)

            # Store checkout data in context
            context.data["git-checkout"] = {
                "branch": branch,
                "checked_out_repos": checked_out_repos,
            }
            logger.debug("Stored git-checkout data for workflow %s", context.adw_id)

            logger.info("Git checkout complete: branch=%s", branch)
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
            error_msg = f"Unexpected error during git checkout: {type(e).__name__}: {e}"
            logger.exception("Unexpected error during git checkout")
            return StepResult.fail(error_msg)
