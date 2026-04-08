"""Shared constants and helper functions for workflow modules."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from rouge.core.utils import get_logger

if TYPE_CHECKING:
    from rouge.core.workflow.step_base import WorkflowContext

# Agent names
AGENT_PLANNER = "sdlc_planner"
AGENT_PLAN_IMPLEMENTOR = "sdlc_plan_implementor"
AGENT_CODE_QUALITY_CHECKER = "sdlc_code_quality_checker"
AGENT_PULL_REQUEST_BUILDER = "sdlc_pull_request_builder"
AGENT_COMMIT_COMPOSER = "commit_composer"

# Step names
IMPLEMENT_PLAN_STEP_NAME = "Implementing plan-based solution"


def get_repo_paths() -> list[str]:
    """Get repository root paths from environment or current directory.

    Reads REPO_PATH, splits on ",", strips each element, and filters empty
    strings.  Returns ``[os.getcwd()]`` when the result is empty (i.e. the
    variable is unset or blank).

    Returns:
        List of repository root paths, defaults to [os.getcwd()] if not set
    """
    raw = os.getenv("REPO_PATH", "")
    paths = [p.strip() for p in raw.split(",")]
    paths = [p for p in paths if p]
    return paths if paths else [os.getcwd()]


def get_working_dir() -> str:
    """Get working directory from environment or current directory.

    Returns:
        Working directory path, defaults to current directory if not set
    """
    return os.getenv("WORKING_DIR", os.getcwd())


def get_affected_repo_paths(
    context: WorkflowContext,
) -> list[str]:
    """Return repo paths that the Implement step actually changed.

    Reads implement_data from context.data and returns the intersection of
    affected_repos with context.repo_paths (preserving original order).
    Falls back to context.repo_paths if no affected_repos data exists.
    """
    implement_data = context.get_optional_step_data("implement_data")
    if implement_data is None or not implement_data.affected_repos:
        return list(context.repo_paths)  # fallback: all repos

    logger = get_logger(context.adw_id)
    affected_set = {r.repo_path for r in implement_data.affected_repos}
    extra = affected_set - set(context.repo_paths)
    if extra:
        logger.warning("affected_repos contains paths not in context.repo_paths: %s", extra)
    return [p for p in context.repo_paths if p in affected_set]


def has_branch_delta(repo_path: str, adw_id: str) -> bool:
    """Check if repo has commits ahead of its remote base branch.

    Returns True if there are commits on HEAD not reachable from the remote
    base branch. Returns True on error to allow PR/MR creation to proceed.
    """
    logger = get_logger(adw_id)
    try:
        base_branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
        )
        base_branch = (
            base_branch_result.stdout.strip().removeprefix("origin/")
            if base_branch_result.returncode == 0
            else "main"
        )
        delta_result = subprocess.run(
            ["git", "rev-list", "--count", f"origin/{base_branch}..HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=30,
        )
        if delta_result.returncode == 0 and delta_result.stdout.strip() == "0":
            return False
        if delta_result.returncode != 0:
            logger.debug(
                "rev-list returned %d for %s, defaulting to has-delta=True",
                delta_result.returncode,
                repo_path,
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(
            "Branch-delta check failed for %s: %s, continuing with creation",
            repo_path,
            e,
        )
    return True
