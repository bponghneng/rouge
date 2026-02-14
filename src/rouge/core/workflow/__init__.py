"""Workflow orchestration package for Rouge ADW process.

This package provides a modular, pluggable pipeline architecture for the Rouge
workflow, where each step implements a common WorkflowStep interface.

Main components:
- runner: Main orchestration logic (execute_workflow)
- pipeline: WorkflowRunner orchestrator and step pipeline
- step_base: Abstract WorkflowStep base class and WorkflowContext
- steps/: Individual step implementations (fetch, classify, plan, etc.)
- status: Issue status updates
- shared: Common constants and helper functions
- types: Unified result types for consistent error handling
- workflow_io: Shared I/O utilities for steps
- workflow_registry: Workflow type registry for pipeline routing

Note: Business logic has been moved from top-level modules (classify, plan, implement,
review, acceptance, address_review) into their respective step classes in steps/.
"""

# Import and re-export public API
from rouge.core.workflow.pipeline import WorkflowRunner, get_default_pipeline
from rouge.core.workflow.runner import execute_workflow
from rouge.core.workflow.status import update_status
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import (
    ClassifyData,
    ImplementData,
    PlanData,
    ReviewData,
    StepResult,
)
from rouge.core.workflow.workflow_registry import WorkflowRegistry, get_pipeline_for_type

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
    # Unified types
    "StepResult",
    "ClassifyData",
    "PlanData",
    "ImplementData",
    "ReviewData",
    # Workflow registry
    "get_pipeline_for_type",
    "WorkflowRegistry",
]
