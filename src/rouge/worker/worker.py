#!/usr/bin/env python3
"""
Rouge Issue Worker Daemon

A standalone daemon that continuously polls the issues database table for pending
issues and executes the appropriate workflows using the rouge-adw command. The worker
operates independently of the CLI, providing automated background processing of issues
with proper locking mechanisms to prevent race conditions between multiple worker instances.

Usage:
    python -m rouge-worker --worker-id <worker_id> [--poll-interval <seconds>] [--log-level <level>]

Example:
    python -m rouge-worker --worker-id alleycat-1 --poll-interval 10 --log-level INFO
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from types import FrameType

from rouge.core.database import fetch_issue, init_db_env
from rouge.core.utils import make_adw_id

from .config import WorkerConfig
from .database import get_next_issue, update_issue_status


class IssueWorker:
    """Worker daemon that processes pending issues from the database."""

    def __init__(self, config: WorkerConfig):
        """
        Initialize the issue worker.

        Args:
            config: WorkerConfig instance with worker settings
        """
        self.config = config
        self.running = True
        self._working_dir_note = None
        if self.config.working_dir is not None:
            os.chdir(self.config.working_dir)
            self._working_dir_note = f"Working directory set to {self.config.working_dir}"
            # Re-initialize env vars from the new working directory
            # This ensures we pick up the .env file from the target directory
            # First try the working directory itself, then its parent
            env_file_path = Path(self.config.working_dir) / ".env"
            if env_file_path.is_file():
                init_db_env(dotenv_path=env_file_path)
            else:
                env_file_path = Path(self.config.working_dir).parent / ".env"
                if env_file_path.is_file():
                    init_db_env(dotenv_path=env_file_path)
                else:
                    # Fallback to default load_dotenv behavior if not found
                    init_db_env()

        self.logger = self.setup_logging()
        if self._working_dir_note:
            self.logger.info(self._working_dir_note)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        self.logger.info("Worker %s initialized", self.config.worker_id)
        self.logger.info("Poll interval: %s seconds", self.config.poll_interval)

    def setup_logging(self) -> logging.Logger:
        """
        Configure logging for the worker.

        Sets up both file and console handlers with appropriate formatting.

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(f"rouge_worker_{self.config.worker_id}")
        logger.setLevel(getattr(logging, self.config.log_level))

        # Create logs directory if it doesn't exist
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)

        # File handler
        log_file = log_dir / f"worker_{self.config.worker_id}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, self.config.log_level))

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def _handle_shutdown(self, signum: int, _frame: FrameType | None) -> None:
        """Handle shutdown signals gracefully."""
        self.logger.info("Received signal %s, shutting down gracefully...", signum)
        self.running = False

    def _get_base_cmd(self) -> list:
        """Get the base command for running rouge-adw.

        Returns:
            List of command components to execute rouge-adw
        """
        # Check if rouge-adw is in PATH (e.g. global install)
        if shutil.which("rouge-adw"):
            return ["rouge-adw"]
        # Fallback to uv run (development mode)
        return ["uv", "run", "rouge-adw"]

    def _handle_workflow_failure(self, issue_id: int, workflow_type: str, reason: str) -> None:
        """Handle workflow failure by logging with exception context.

        Args:
            issue_id: The ID of the issue
            workflow_type: The type of workflow that failed
            reason: Description of the failure reason
        """
        self.logger.exception(
            "%s workflow failed for issue %s: %s", workflow_type.capitalize(), issue_id, reason
        )

    def _execute_workflow(
        self, issue_id: int, workflow_type: str, description: str = ""
    ) -> tuple[str, bool]:
        """Execute a rouge-adw workflow for the given issue.

        Handles all workflow types by determining the adw_id and building the
        appropriate command with --workflow-type.

        Args:
            issue_id: The ID of the issue to process
            workflow_type: The workflow type (e.g. "main", "patch")
            description: The issue description (used for logging on non-patch types)

        Returns:
            Tuple of (adw_id, success) where success is True if workflow completed

        Raises:
            ValueError: If patch issue has no adw_id
            subprocess.TimeoutExpired: If workflow times out
            Exception: If workflow execution fails
        """
        adw_id = None
        try:
            if workflow_type == "patch":
                # Fetch the issue to get adw_id directly from the issues row
                # Note: The Pydantic validator ensures adw_id is trimmed and non-empty if not None
                issue = fetch_issue(issue_id)
                if issue.adw_id is None:
                    raise ValueError(f"Issue {issue_id} has no adw_id")

                adw_id = issue.adw_id.strip()
                if not adw_id:
                    raise ValueError(f"Issue {issue_id} has no adw_id")

                self.logger.info(
                    "Executing %s workflow %s for issue %s", workflow_type, adw_id, issue_id
                )
                self.logger.debug("Issue description: %s", issue.description)
            else:
                # For "main" and any other type, generate a new adw_id
                adw_id = make_adw_id()
                self.logger.info(
                    "Executing %s workflow %s for issue %s", workflow_type, adw_id, issue_id
                )
                self.logger.debug("Issue description: %s", description)

            cmd = self._get_base_cmd() + [
                "--adw-id",
                adw_id,
                "--workflow-type",
                workflow_type,
                str(issue_id),
            ]

            # Execute the workflow with a timeout
            # Note: Not capturing output allows real-time logging from rouge-adw
            # Use configured working directory if set; otherwise fall back to current cwd
            result = subprocess.run(
                cmd,
                timeout=self.config.workflow_timeout,
                cwd=self.config.working_dir or Path.cwd(),
            )

            if result.returncode == 0:
                self.logger.info(
                    "Successfully completed %s workflow %s for issue %s",
                    workflow_type,
                    adw_id,
                    issue_id,
                )
                update_issue_status(issue_id, "completed", self.logger)
                return adw_id, True
            else:
                self.logger.error(
                    "%s workflow %s failed for issue %s with exit code %s",
                    workflow_type.capitalize(),
                    adw_id,
                    issue_id,
                    result.returncode,
                )
                update_issue_status(issue_id, "pending", self.logger)
                return adw_id, False

        except ValueError:
            self._handle_workflow_failure(issue_id, workflow_type, "ValueError during workflow")
            update_issue_status(issue_id, "pending", self.logger)
            return adw_id, False
        except subprocess.TimeoutExpired:
            self._handle_workflow_failure(issue_id, workflow_type, "Workflow timed out")
            update_issue_status(issue_id, "pending", self.logger)
            return adw_id, False
        except Exception:
            self._handle_workflow_failure(issue_id, workflow_type, "Unexpected error in workflow")
            update_issue_status(issue_id, "pending", self.logger)
            return adw_id, False

    def execute_workflow(
        self, issue_id: int, description: str, _status: str, issue_type: str
    ) -> bool:
        """
        Execute the appropriate workflow for the given issue based on type.

        Delegates to _execute_workflow with the issue_type as the workflow_type,
        which determines how the adw_id is resolved and which --workflow-type flag
        is passed to rouge-adw.

        Args:
            issue_id: The ID of the issue to process
            description: The issue description
            _status: The issue status (unused, kept for interface compatibility)
            issue_type: The workflow type (e.g. 'main', 'patch') passed to rouge-adw

        Returns:
            True if workflow executed successfully, False otherwise
        """
        _, success = self._execute_workflow(issue_id, issue_type, description)
        return success

    def run(self) -> None:
        """
        Main worker loop.

        Continuously polls for pending issues and executes workflows.
        Sleeps for the configured poll interval when no issues are available.
        """
        self.logger.info("Worker %s starting main loop", self.config.worker_id)

        while self.running:
            try:
                # Get next issue (returns tuple of issue_id, description, status, type)
                issue = get_next_issue(self.config.worker_id, self.logger)

                if issue:
                    issue_id, description, status, issue_type = issue
                    self.execute_workflow(issue_id, description, status, issue_type)
                else:
                    # No issues available, sleep for poll interval
                    self.logger.debug(
                        "No pending issues, sleeping for %s seconds", self.config.poll_interval
                    )
                    time.sleep(self.config.poll_interval)

            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, shutting down...")
                self.running = False

            except Exception as e:
                self.logger.error("Unexpected error in main loop: %s", e)
                time.sleep(self.config.poll_interval)

        self.logger.info("Worker %s stopped", self.config.worker_id)
