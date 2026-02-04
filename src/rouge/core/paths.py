"""
Rouge directory structure management.

This module provides centralized path management for runtime directories
using get_working_dir() as the single source of truth for the base path.
"""

from pathlib import Path

from rouge.core.workflow.shared import get_working_dir


class RougePaths:
    """Manage Rouge directory structure using get_working_dir() as base path."""

    @staticmethod
    def get_base_dir() -> Path:
        """Get base Rouge directory."""
        return Path(get_working_dir()) / ".rouge"

    @staticmethod
    def get_logs_dir() -> Path:
        """Get logs directory for workflow logs."""
        return RougePaths.get_base_dir() / "logs"

    @staticmethod
    def get_workflows_dir() -> Path:
        """Get workflows directory for artifact storage."""
        return RougePaths.get_base_dir() / "workflows"

    @staticmethod
    def get_workflow_dir(workflow_id: str) -> Path:
        """Get directory for a specific workflow's artifacts.

        Args:
            workflow_id: The workflow ID

        Returns:
            Path to the workflow artifact directory
        """
        return RougePaths.get_workflows_dir() / workflow_id

    @staticmethod
    def ensure_directories() -> None:
        """
        Ensure all required directories exist with proper permissions.

        Creates directories atomically with 0700 permissions.
        """
        directories = [
            RougePaths.get_logs_dir(),
            RougePaths.get_workflows_dir(),
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
