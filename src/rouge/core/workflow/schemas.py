"""JSON Schema definitions for workflow step outputs.

This module defines JSON Schema constants for validating structured outputs
from various workflow steps. These schemas are used with the Claude provider
to enforce structured JSON responses from the LLM.

Each schema corresponds to a specific workflow step and defines the expected
output structure based on the required fields defined in the respective
workflow step modules.
"""

# JSON Schema for classify step output
# Expected fields: type (chore|bug|feature), level (simple|average|complex|critical)
CLASSIFY_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "type": {
      "type": "string",
      "enum": ["chore", "bug", "feature"],
      "description": "The type of issue being classified"
    },
    "level": {
      "type": "string",
      "enum": ["simple", "average", "complex", "critical"],
      "description": "The complexity level of the issue"
    }
  },
  "required": ["type", "level"],
  "additionalProperties": false
}"""

# JSON Schema for plan and patch-plan step output
# Expected fields: output, plan, summary
PLAN_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "output": {
      "type": "string",
      "description": "The raw output from the planning process"
    },
    "plan": {
      "type": "string",
      "description": "The implementation plan content in markdown format"
    },
    "summary": {
      "type": "string",
      "description": "A brief summary of the plan"
    }
  },
  "required": ["output", "plan", "summary"],
  "additionalProperties": false
}"""

# JSON Schema for acceptance step output
# Expected fields: output, notes, plan_title, requirements, status, summary,
# unmet_blocking_requirements
ACCEPTANCE_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "output": {
      "type": "string",
      "description": "The raw output from the acceptance validation"
    },
    "notes": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Notes from the acceptance validation"
    },
    "plan_title": {
      "type": "string",
      "description": "Title of the validated plan"
    },
    "requirements": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "requirement": {
            "type": "string",
            "description": "The requirement text"
          },
          "status": {
            "type": "string",
            "enum": ["met", "unmet", "partial"],
            "description": "Whether the requirement is met"
          },
          "blocking": {
            "type": "boolean",
            "description": "Whether this requirement is blocking"
          }
        },
        "required": ["requirement", "status"]
      },
      "description": "List of requirements and their validation status"
    },
    "status": {
      "type": "string",
      "enum": ["accepted", "rejected", "needs_revision"],
      "description": "Overall acceptance status"
    },
    "summary": {
      "type": "string",
      "description": "Summary of the acceptance validation"
    },
    "unmet_blocking_requirements": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "List of unmet requirements that are blocking"
    }
  },
  "required": [
    "output", "notes", "plan_title", "requirements",
    "status", "summary", "unmet_blocking_requirements"
  ],
  "additionalProperties": false
}"""

# JSON Schema for code-quality step output
# Expected fields: output, tools
CODE_QUALITY_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "output": {
      "type": "string",
      "description": "The raw output from the code quality checks"
    },
    "tools": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "description": "Name of the code quality tool"
          },
          "status": {
            "type": "string",
            "enum": ["passed", "failed", "skipped"],
            "description": "Result status of the tool"
          },
          "output": {
            "type": "string",
            "description": "Output from the tool"
          }
        },
        "required": ["name", "status"]
      },
      "description": "List of code quality tools that were run"
    }
  },
  "required": ["output", "tools"],
  "additionalProperties": false
}"""

# JSON Schema for compose-commits step output
# Expected fields: output
COMPOSE_COMMITS_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "output": {
      "type": "string",
      "description": "The raw output from the commit composition process"
    }
  },
  "required": ["output"],
  "additionalProperties": false
}"""

# JSON Schema for implement-plan step output
# Expected fields: files_modified, git_diff_stat, output, status, summary
IMPLEMENT_PLAN_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "files_modified": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "List of files that were modified during implementation"
    },
    "git_diff_stat": {
      "type": "string",
      "description": "Git diff statistics showing changes made"
    },
    "output": {
      "type": "string",
      "description": "The raw output from the implementation process"
    },
    "status": {
      "type": "string",
      "enum": ["success", "partial", "failed"],
      "description": "Status of the implementation"
    },
    "summary": {
      "type": "string",
      "description": "Summary of the implementation changes"
    }
  },
  "required": ["files_modified", "git_diff_stat", "output", "status", "summary"],
  "additionalProperties": false
}"""

# JSON Schema for implement-review step output
# Expected fields: issues, output, summary
IMPLEMENT_REVIEW_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "issue": {
            "type": "string",
            "description": "Description of the review issue"
          },
          "resolution": {
            "type": "string",
            "description": "How the issue was resolved"
          },
          "status": {
            "type": "string",
            "enum": ["resolved", "unresolved", "deferred"],
            "description": "Status of the issue resolution"
          }
        },
        "required": ["issue", "resolution", "status"]
      },
      "description": "List of review issues that were addressed"
    },
    "output": {
      "type": "string",
      "description": "The raw output from the review implementation"
    },
    "summary": {
      "type": "string",
      "description": "Summary of the review implementation"
    }
  },
  "required": ["issues", "output", "summary"],
  "additionalProperties": false
}"""

# JSON Schema for pull-request step output
# Expected fields: output, title, summary, commits
PULL_REQUEST_JSON_SCHEMA = """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "output": {
      "type": "string",
      "description": "The raw output from the pull request preparation"
    },
    "title": {
      "type": "string",
      "description": "Title for the pull request"
    },
    "summary": {
      "type": "string",
      "description": "Summary/description for the pull request body"
    },
    "commits": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "hash": {
            "type": "string",
            "description": "The commit hash"
          },
          "message": {
            "type": "string",
            "description": "The commit message"
          }
        },
        "required": ["hash", "message"]
      },
      "description": "List of commits to include in the pull request"
    }
  },
  "required": ["output", "title", "summary", "commits"],
  "additionalProperties": false
}"""
