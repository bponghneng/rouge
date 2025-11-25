"""Workflow orchestration package for Cape ADW process.

This package provides a modular structure for the Cape workflow pipeline,
breaking down the monolithic workflow into focused, maintainable modules.

Main components:
- runner: Main orchestration logic (execute_workflow)
- classify: Issue classification
- plan: Plan building
- plan_file: Plan file extraction
- implement: Implementation execution with JSON parsing
- review: CodeRabbit review generation and notification
- status: Issue status updates
- shared: Common constants and helper functions
"""

# Import and re-export public API for backward compatibility
from cape.core.workflow.classify import classify_issue
from cape.core.workflow.implement import implement_plan
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.runner import execute_workflow
from cape.core.workflow.status import update_status

# Export public API
__all__ = [
    "execute_workflow",
    "update_status",
    "classify_issue",
    "build_plan",
    "get_plan_file",
    "implement_plan",
]
