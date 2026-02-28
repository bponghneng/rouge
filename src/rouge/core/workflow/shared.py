"""Shared constants and helper functions for workflow modules."""

import logging
import os
from typing import Dict

logger = logging.getLogger(__name__)

# Agent names
AGENT_CLASSIFIER = "issue_classifier"
AGENT_PLANNER = "sdlc_planner"
AGENT_PLAN_FINDER = "plan_finder"
AGENT_PLAN_IMPLEMENTOR = "sdlc_plan_implementor"
AGENT_REVIEW_IMPLEMENTOR = "sdlc_review_implementor"
AGENT_VALIDATOR = "sdlc_validator"
AGENT_CODE_QUALITY_CHECKER = "sdlc_code_quality_checker"
AGENT_PATCH_PLANNER = "patch_planner"
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


def get_max_acceptance_iterations() -> int:
    """Get maximum acceptance iterations from environment or use default.

    Returns:
        Maximum number of acceptance iterations, defaults to 3 if not set or invalid
    """
    env_value = os.getenv("MAX_ACCEPTANCE_ITERATIONS", "3")
    try:
        max_iterations = int(env_value)
        if max_iterations < 1:
            logger.warning(
                "MAX_ACCEPTANCE_ITERATIONS must be >= 1, got %s. " "Using default value 3.",
                max_iterations,
            )
            return 3
        return max_iterations
    except ValueError:
        logger.warning(
            "Failed to parse MAX_ACCEPTANCE_ITERATIONS='%s' as integer. " "Using default value 3.",
            env_value,
        )
        return 3


def derive_paths_from_plan(plan_path: str) -> Dict[str, str]:
    """Extract type and slug from plan file path and derive related paths.

    Args:
        plan_path: Path to the plan file (e.g., specs/chore-foo-plan.md)

    Returns:
        Dictionary with type, slug, plan_file, and review_file paths
    """
    # Extract filename from path
    filename = os.path.basename(plan_path)

    # Default values if parsing fails
    result = {"type": "", "slug": "", "plan_file": plan_path, "review_file": ""}

    # Parse type and slug from filename
    # Expected format: {type}-{slug}-plan.md
    if filename.endswith("-plan.md"):
        # Remove the -plan.md suffix
        base_name = filename[:-8]  # Remove "-plan.md"

        # Split by first hyphen to get type
        parts = base_name.split("-", 1)
        if len(parts) >= 2:
            result["type"] = parts[0]
            result["slug"] = parts[1]

            # Build canonical paths
            result["plan_file"] = f"specs/{result['type']}-{result['slug']}-plan.md"
            result["review_file"] = f"specs/{result['type']}-{result['slug']}-review.txt"
        elif len(parts) == 1:
            # Handle case where there's no slug (shouldn't happen but be safe)
            result["type"] = parts[0]
            result["slug"] = ""
            result["plan_file"] = f"specs/{result['type']}-plan.md"
            result["review_file"] = f"specs/{result['type']}-review.txt"

    return result
