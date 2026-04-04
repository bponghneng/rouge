"""Shared helper for filtering repositories to those affected by implementation."""

from typing import Optional, Tuple

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import ImplementArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.types import ImplementData


def get_affected_repos(
    context: WorkflowContext,
) -> Tuple[list[str], Optional[ImplementData]]:
    """Load ImplementArtifact and return filtered repo list.

    Returns:
        Tuple of (affected_repo_paths, implement_data).
        If implement artifact is missing or has no affected_repos,
        returns ([], None).

    The returned repo list preserves the order from context.repo_paths,
    filtered to only repos present in implement_data.affected_repos.
    Validates that affected_repos is a subset of context.repo_paths.
    """
    logger = get_logger(context.adw_id)

    implement_data = context.load_optional_artifact(
        "implement_data",
        "implement",
        ImplementArtifact,
        lambda a: a.implement_data,
    )

    if implement_data is None:
        logger.debug("No implement artifact found; returning empty affected repos")
        return [], None

    affected_set = set(implement_data.affected_repos)

    # Warn about unknown repos in affected_repos
    known_set = set(context.repo_paths)
    unknown = affected_set - known_set
    if unknown:
        logger.warning(
            "affected_repos contains paths not in context.repo_paths: %s",
            unknown,
        )

    # Filter context.repo_paths preserving order
    filtered = [rp for rp in context.repo_paths if rp in affected_set]

    if not filtered:
        logger.info("No repos affected by implementation")

    return filtered, implement_data
