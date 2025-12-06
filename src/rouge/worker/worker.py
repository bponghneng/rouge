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
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

from rouge.core.database import init_db_env
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
                init_db_env(dotenv_path=str(env_file_path))
            else:
                env_file_path = Path(self.config.working_dir).parent / ".env"
                if env_file_path.is_file():
                    init_db_env(dotenv_path=str(env_file_path))
                else:
                    # Fallback to default load_dotenv behavior if not found
                    init_db_env()

        self.logger = self.setup_logging()
        if self._working_dir_note:
            self.logger.info(self._working_dir_note)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        self.logger.info(f"Worker {self.config.worker_id} initialized")
        self.logger.info(f"Poll interval: {self.config.poll_interval} seconds")

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

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def execute_workflow(self, issue_id: int, description: str) -> bool:
        """
        Execute the rouge-adw workflow for the given issue.

        Args:
            issue_id: The ID of the issue to process
            description: The issue description

        Returns:
            True if workflow executed successfully, False otherwise
        """
        self.logger.info(f"Executing workflow for issue {issue_id}")
        self.logger.debug(f"Issue description: {description}")

        try:
            workflow_id = make_adw_id()
            # Build the command to execute
            # Note: Options must come before positional arguments in Typer/Click

            # Determine command to run
            # Check for explicit override
            adw_cmd = os.environ.get("ROUGE_ADW_COMMAND")
            if adw_cmd:
                base_cmd = shlex.split(adw_cmd)
            # Check if rouge-adw is in PATH (e.g. global install)
            elif shutil.which("rouge-adw"):
                base_cmd = ["rouge-adw"]
            # Fallback to uv run (development mode)
            else:
                base_cmd = ["uv", "run", "rouge-adw"]

            cmd = base_cmd + [
                "--adw-id",
                workflow_id,
                str(issue_id),
            ]

            # Execute the workflow with a timeout
            # Note: Not capturing output allows real-time logging from rouge-adw
            app_root = Path(os.environ.get("ROUGE_APP_ROOT", Path.cwd()))

            result = subprocess.run(
                cmd,
                timeout=self.config.workflow_timeout,
                cwd=app_root,
            )

            if result.returncode == 0:
                self.logger.info(
                    f"Successfully completed issue {issue_id} (workflow {workflow_id})"
                )
                update_issue_status(issue_id, "completed", self.logger)
                return True
            else:
                self.logger.error(
                    f"Workflow {workflow_id} failed for issue {issue_id} "
                    f"with exit code {result.returncode}"
                )
                update_issue_status(issue_id, "pending", self.logger)
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"Workflow timed out for issue {issue_id}")
            update_issue_status(issue_id, "pending", self.logger)
            return False

        except Exception as e:
            self.logger.error(f"Error executing workflow for issue {issue_id}: {e}")
            update_issue_status(issue_id, "pending", self.logger)
            return False

    def run(self) -> None:
        """
        Main worker loop.

        Continuously polls for pending issues and executes workflows.
        Sleeps for the configured poll interval when no issues are available.
        """
        self.logger.info(f"Worker {self.config.worker_id} starting main loop")

        while self.running:
            try:
                # Get next issue
                issue = get_next_issue(self.config.worker_id, self.logger)

                if issue:
                    issue_id, description = issue
                    self.execute_workflow(issue_id, description)
                else:
                    # No issues available, sleep for poll interval
                    self.logger.debug(
                        f"No pending issues, sleeping for {self.config.poll_interval} seconds"
                    )
                    time.sleep(self.config.poll_interval)

            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, shutting down...")
                self.running = False

            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(self.config.poll_interval)

        self.logger.info(f"Worker {self.config.worker_id} stopped")
