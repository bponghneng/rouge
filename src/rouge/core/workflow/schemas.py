"""JSON schema constants for workflow step outputs.

These schemas are used with Claude CLI's --json-schema flag to enforce
structured output from agent responses. Each schema defines the expected
JSON structure for a specific workflow step.

Usage:
    import json
    from rouge.core.workflow.schemas import CLASSIFY_SCHEMA

    schema_str = json.dumps(CLASSIFY_SCHEMA)
    # Pass schema_str to --json-schema flag
"""

from typing import Any, Dict

# Schema for classify step output
# Expected fields: type (issue type), level (complexity level)
CLASSIFY_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "description": "Issue type classification",
            "enum": ["chore", "bug", "feature"],
        },
        "level": {
            "type": "string",
            "description": "Complexity level classification",
            "enum": ["simple", "average", "complex", "critical"],
        },
    },
    "required": ["type", "level"],
    "additionalProperties": False,
}

# Schema for plan step output (used by all plan variants: chore, bug, feature, patch)
# Expected fields: output (raw output), plan (implementation plan), summary (brief summary)
PLAN_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "output": {
            "type": "string",
            "description": "Raw output from the planning process",
        },
        "plan": {
            "type": "string",
            "description": "The implementation plan content in markdown format",
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the plan",
        },
    },
    "required": ["output", "plan", "summary"],
    "additionalProperties": True,
}

# Schema for patch_plan step output (same structure as plan)
# Patch plans are standalone implementation plans built from patch issue descriptions
PATCH_PLAN_SCHEMA: Dict[str, Any] = PLAN_SCHEMA

# Schema for implement step output
# Expected fields: files_modified, git_diff_stat, output, status, summary
IMPLEMENT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "files_modified": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of file paths that were modified",
        },
        "git_diff_stat": {
            "type": "string",
            "description": "Git diff stat output showing changes",
        },
        "output": {
            "type": "string",
            "description": "Raw output from the implementation process",
        },
        "status": {
            "type": "string",
            "description": "Implementation status (success, partial, failed)",
            "enum": ["success", "partial", "failed"],
        },
        "summary": {
            "type": "string",
            "description": "Summary of the implementation work done",
        },
    },
    "required": ["files_modified", "git_diff_stat", "output", "status", "summary"],
    "additionalProperties": True,
}

# Schema for implement_review step output (address_review)
# Expected fields: issues, output, summary
IMPLEMENT_REVIEW_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "resolution": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["description", "resolution", "status"],
            },
            "description": "List of review issues that were addressed",
        },
        "output": {
            "type": "string",
            "description": "Raw output from the review addressing process",
        },
        "summary": {
            "type": "string",
            "description": "Summary of how review issues were addressed",
        },
    },
    "required": ["issues", "output", "summary"],
    "additionalProperties": True,
}

# Schema for code_quality step output
# Expected fields: output, tools
CODE_QUALITY_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "output": {
            "type": "string",
            "description": "Raw output from code quality checks",
        },
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "output": {"type": "string"},
                },
                "required": ["name", "status"],
            },
            "description": "List of quality tools that were run with their results",
        },
    },
    "required": ["output", "tools"],
    "additionalProperties": True,
}

# Schema for acceptance step output
# Expected fields: output, notes, plan_title, requirements, status, summary,
# unmet_blocking_requirements
ACCEPTANCE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "output": {
            "type": "string",
            "description": "Raw output from the acceptance validation",
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional notes from the acceptance review",
        },
        "plan_title": {
            "type": "string",
            "description": "Title of the plan being validated",
        },
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "met": {"type": "boolean"},
                    "blocking": {"type": "boolean"},
                },
                "required": ["description", "met"],
            },
            "description": "List of requirements with their validation status",
        },
        "status": {
            "type": "string",
            "description": "Overall acceptance status",
            "enum": ["accepted", "rejected", "partial"],
        },
        "summary": {
            "type": "string",
            "description": "Summary of the acceptance validation",
        },
        "unmet_blocking_requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of unmet requirements that block acceptance",
        },
    },
    "required": [
        "output",
        "notes",
        "plan_title",
        "requirements",
        "status",
        "summary",
        "unmet_blocking_requirements",
    ],
    "additionalProperties": True,
}

# Schema for pull_request step output
# Expected fields: output, title, summary, commits
PULL_REQUEST_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "output": {
            "type": "string",
            "description": "Raw output from the PR preparation process",
        },
        "title": {
            "type": "string",
            "description": "Pull request title",
        },
        "summary": {
            "type": "string",
            "description": "Pull request description/summary",
        },
        "commits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["message"],
            },
            "description": "List of commits to include in the PR",
        },
    },
    "required": ["output", "title", "summary", "commits"],
    "additionalProperties": True,
}

# Schema for compose_commits step output
# Expected fields: output
COMPOSE_COMMITS_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "output": {
            "type": "string",
            "description": "Raw output from the commit composition process",
        },
    },
    "required": ["output"],
    "additionalProperties": True,
}

# Mapping of step names to their schemas for convenience
STEP_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "classify": CLASSIFY_SCHEMA,
    "plan": PLAN_SCHEMA,
    "patch_plan": PATCH_PLAN_SCHEMA,
    "implement": IMPLEMENT_SCHEMA,
    "implement_review": IMPLEMENT_REVIEW_SCHEMA,
    "code_quality": CODE_QUALITY_SCHEMA,
    "acceptance": ACCEPTANCE_SCHEMA,
    "pull_request": PULL_REQUEST_SCHEMA,
    "compose_commits": COMPOSE_COMMITS_SCHEMA,
}
