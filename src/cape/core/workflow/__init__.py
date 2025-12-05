"""Workflow orchestration package for Cape ADW process.

This package provides a modular, pluggable pipeline architecture for the Cape
workflow, where each step implements a common WorkflowStep interface.

Main components:
- runner: Main orchestration logic (execute_workflow)
- pipeline: WorkflowRunner orchestrator and step pipeline
- step_base: Abstract WorkflowStep base class and WorkflowContext
- steps/: Individual step implementations (fetch, classify, plan, etc.)
- classify: Issue classification
- plan: Plan building
- plan_file: Plan file extraction
- implement: Implementation execution with JSON parsing
- review: CodeRabbit review generation and notification
- status: Issue status updates
- shared: Common constants and helper functions
- types: Unified result types for consistent error handling
- workflow_io: Shared I/O utilities for steps
"""

# Import and re-export public API for backward compatibility
from cape.core.workflow.classify import classify_issue
from cape.core.workflow.implement import implement_plan
from cape.core.workflow.pipeline import WorkflowRunner, get_default_pipeline
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.runner import execute_workflow
from cape.core.workflow.status import update_status
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import (
    ClassifyData,
    ImplementData,
    PlanData,
    PlanFileData,
    ReviewData,
    StepResult,
)

# Export public API
__all__ = [
    # Main entry point
    "execute_workflow",
    # Pipeline components
    "WorkflowRunner",
    "WorkflowStep",
    "WorkflowContext",
    "get_default_pipeline",
    # Individual workflow functions
    "update_status",
    "classify_issue",
    "build_plan",
    "get_plan_file",
    "implement_plan",
    # Unified types
    "StepResult",
    "ClassifyData",
    "PlanData",
    "PlanFileData",
    "ImplementData",
    "ReviewData",
]
