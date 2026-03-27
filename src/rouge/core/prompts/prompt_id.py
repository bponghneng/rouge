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
    COMPOSE_COMMITS = "compose-commits"
    FEATURE_PLAN = "feature-plan"
    IMPLEMENT_PLAN = "implement-plan"
    PATCH_PLAN = "patch-plan"
    PULL_REQUEST = "pull-request"
