"""Shared constants and helper functions for workflow modules."""

import os
from typing import Dict, Optional


# Agent names
AGENT_IMPLEMENTOR = "sdlc_implementor"
AGENT_PLANNER = "sdlc_planner"
AGENT_CLASSIFIER = "issue_classifier"
AGENT_PLAN_FINDER = "plan_finder"


def get_repo_path() -> str:
    """Get repository root path from environment or current directory.

    Returns:
        Repository root path, defaults to current directory if not set
    """
    return os.getenv("REPO_PATH", os.getcwd())


def get_working_dir() -> str:
    """Get working directory from environment or current directory.

    Returns:
        Working directory path, defaults to current directory if not set
    """
    return os.getenv("WORKING_DIR", os.getcwd())


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
    result = {
        "type": "",
        "slug": "",
        "plan_file": plan_path,
        "review_file": ""
    }

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