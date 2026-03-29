"""Shared constants and helper functions for workflow modules."""

import os

# Agent names
AGENT_PLANNER = "sdlc_planner"
AGENT_PLAN_IMPLEMENTOR = "sdlc_plan_implementor"
AGENT_CODE_QUALITY_CHECKER = "sdlc_code_quality_checker"
AGENT_PULL_REQUEST_BUILDER = "sdlc_pull_request_builder"
AGENT_COMMIT_COMPOSER = "commit_composer"

# Step names
IMPLEMENT_STEP_NAME = "Implementing solution"


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
