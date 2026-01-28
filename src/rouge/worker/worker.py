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
from rouge.core.utils import make_adw_id, make_patch_workflow_id

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

    def _execute_main_workflow(self, issue_id: int, description: str) -> tuple[str, bool]:
        """Execute the main rouge-adw workflow for a new issue.

        Args:
            issue_id: The ID of the issue to process
            description: The issue description

        Returns:
            Tuple of (workflow_id, success) where success is True if workflow completed

        Raises:
            subprocess.TimeoutExpired: If workflow times out
            Exception: If workflow execution fails
        """
        workflow_id = make_adw_id()
        self.logger.info("Executing main workflow %s for issue %s", workflow_id, issue_id)
        self.logger.debug("Issue description: %s", description)

        cmd = self._get_base_cmd() + [
            "--adw-id",
            workflow_id,
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
            self.logger.info("Successfully completed issue %s (workflow %s)", issue_id, workflow_id)
            update_issue_status(issue_id, "completed", self.logger)
            return workflow_id, True
        else:
            self.logger.error(
                "Workflow %s failed for issue %s with exit code %s",
                workflow_id,
                issue_id,
                result.returncode,
            )
            update_issue_status(issue_id, "pending", self.logger)
            return workflow_id, False

    def _handle_patch_failure(self, issue_id: int, _reason: str) -> None:
        """Handle patch workflow failure by logging and updating status.

        Args:
            issue_id: The ID of the issue
            _reason: Description of the failure reason
        """
        self.logger.exception("Patch workflow failed for issue %s", issue_id)

    def _execute_patch_workflow(self, issue_id: int) -> tuple[str, bool]:
        """Execute the patch workflow for an issue of type 'patch'.

        Args:
            issue_id: The ID of the patch issue to process

        Returns:
            Tuple of (patch_workflow_id, success) where success is True if completed

        Raises:
            ValueError: If issue not found or adw_id missing
            subprocess.TimeoutExpired: If workflow times out
            Exception: If workflow execution fails
        """
        try:
            # Fetch the issue to get adw_id directly from the issues row
            # Note: The Pydantic validator ensures adw_id is trimmed and non-empty if not None
            issue = fetch_issue(issue_id)
            if issue.adw_id is None:
                raise ValueError(f"Issue {issue_id} has no adw_id")

            # For patch issues, the adw_id is the main ADW ID from the parent
            main_adw_id = issue.adw_id
            patch_wf_id = make_patch_workflow_id(main_adw_id)

            self.logger.info(
                "Executing patch workflow %s for issue %s (derived from %s)",
                patch_wf_id,
                issue_id,
                main_adw_id,
            )
            self.logger.debug("Issue description: %s", issue.description)

            cmd = self._get_base_cmd() + [
                "--adw-id",
                patch_wf_id,
                "--patch-mode",
                str(issue_id),
            ]

            # Execute the workflow with a timeout
            result = subprocess.run(
                cmd,
                timeout=self.config.workflow_timeout,
                cwd=self.config.working_dir or Path.cwd(),
            )

            if result.returncode == 0:
                self.logger.info(
                    "Successfully completed patch workflow %s for issue %s",
                    patch_wf_id,
                    issue_id,
                )
                update_issue_status(issue_id, "completed", self.logger)
                return patch_wf_id, True
            else:
                self.logger.error(
                    "Patch workflow %s failed for issue %s with exit code %s",
                    patch_wf_id,
                    issue_id,
                    result.returncode,
                )
                update_issue_status(issue_id, "pending", self.logger)
                return patch_wf_id, False

        except ValueError:
            self._handle_patch_failure(issue_id, "ValueError during patch workflow")
            raise
        except subprocess.TimeoutExpired:
            self._handle_patch_failure(issue_id, "Patch workflow timed out")
            raise
        except Exception:
            self._handle_patch_failure(issue_id, "Unexpected error in patch workflow")
            raise

    def execute_workflow(
        self, issue_id: int, description: str, _status: str, issue_type: str
    ) -> bool:
        """
        Execute the appropriate workflow for the given issue based on type.

        Routes to either main workflow (for 'main' type issues) or patch workflow
        (for 'patch' type issues).

        Args:
            issue_id: The ID of the issue to process
            description: The issue description
            _status: The issue status (unused, kept for interface compatibility)
            issue_type: The issue type ('main' or 'patch') - determines workflow routing

        Returns:
            True if workflow executed successfully, False otherwise
        """
        try:
            if issue_type == "patch":
                _, success = self._execute_patch_workflow(issue_id)
            else:
                _, success = self._execute_main_workflow(issue_id, description)
            return success

        except subprocess.TimeoutExpired:
            self.logger.exception("Workflow timed out for issue %s", issue_id)
            update_issue_status(issue_id, "pending", self.logger)
            return False

        except Exception:
            self.logger.exception("Error executing workflow for issue %s", issue_id)
            update_issue_status(issue_id, "pending", self.logger)
            return False

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
