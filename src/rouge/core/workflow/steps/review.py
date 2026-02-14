"""Review generation and addressing step implementations.

DEPRECATED: This module is maintained for backwards compatibility.
New code should import from:
- rouge.core.workflow.steps.code_review (CodeReviewStep)
- rouge.core.workflow.steps.review_fix (ReviewFixStep)
"""

# Re-export classes from split modules for backwards compatibility
from rouge.core.workflow.steps.code_review import (
    CODE_REVIEW_STEP_NAME,
    CodeReviewStep,
    is_clean_review,
)
from rouge.core.workflow.steps.review_fix import (
    ADDRESS_REVIEW_JSON_SCHEMA,
    ADDRESS_REVIEW_REQUIRED_FIELDS,
    ReviewFixStep,
)

# Backwards compatibility aliases
GENERATE_REVIEW_STEP_NAME = CODE_REVIEW_STEP_NAME
GenerateReviewStep = CodeReviewStep
AddressReviewStep = ReviewFixStep

__all__ = [
    "CODE_REVIEW_STEP_NAME",
    "GENERATE_REVIEW_STEP_NAME",
    "ADDRESS_REVIEW_JSON_SCHEMA",
    "ADDRESS_REVIEW_REQUIRED_FIELDS",
    "is_clean_review",
    "CodeReviewStep",
    "ReviewFixStep",
    "GenerateReviewStep",
    "AddressReviewStep",
]
