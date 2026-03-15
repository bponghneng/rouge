"""Prompt IDs for Rouge-owned workflow prompt templates."""

from enum import Enum


class PromptId(str, Enum):
    """Identifiers for packaged workflow prompt templates.

    Each value corresponds to a template file under
    ``rouge/core/prompts/templates/<value>.md``.
    """

    ACCEPTANCE = "acceptance"
    BUG_PLAN = "bug-plan"
    CHORE_PLAN = "chore-plan"
    CLASSIFY = "classify"
    CLAUDE_CODE_PLAN = "claude-code-plan"
    CODE_QUALITY = "code-quality"
    CODE_REVIEW_SUMMARY = "code-review-summary"
    COMPOSE_COMMITS = "compose-commits"
    FEATURE_PLAN = "feature-plan"
    FIND_PLAN_FILE = "find-plan-file"
    IMPLEMENT_PLAN = "implement-plan"
    IMPLEMENT_REVIEW = "implement-review"
    PATCH_PLAN = "patch-plan"
    PULL_REQUEST = "pull-request"
    REVIEW_PLAN = "review-plan"
