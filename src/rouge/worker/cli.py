"""Command-line interface for the Rouge Worker."""

import argparse
import os
import sys
from pathlib import Path

from .config import WorkerConfig
from .worker import IssueWorker


def main():
    """Parse command line arguments and start the worker."""
    # Safely parse ROUGE_WORKFLOW_TIMEOUT_SECONDS env var
    default_timeout = 3600
    timeout_env = os.environ.get("ROUGE_WORKFLOW_TIMEOUT_SECONDS")
    if timeout_env:
        try:
            default_timeout = int(timeout_env)
        except ValueError:
            print(
                f"Warning: Invalid value for ROUGE_WORKFLOW_TIMEOUT_SECONDS "
                f"'{timeout_env}', using default {default_timeout} seconds",
                file=sys.stderr,
            )

    parser = argparse.ArgumentParser(
        description="Rouge Issue Worker Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m rouge-worker --worker-id alleycat-1
  python -m rouge-worker --worker-id tydirium-1 --poll-interval 5 --log-level DEBUG
        """,
    )

    parser.add_argument(
        "--worker-id",
        required=True,
        help="Unique identifier for this worker instance (e.g., 'alleycat-1')",
    )

    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Number of seconds to wait between polls (default: 10)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--working-dir",
        type=Path,
        default=None,
        help="Absolute directory the worker should switch to before starting.",
    )

    parser.add_argument(
        "--workflow-timeout",
        type=int,
        default=default_timeout,
        help="Timeout in seconds for workflow execution (default: 3600)",
    )

    args = parser.parse_args()

    # Create configuration
    config = WorkerConfig(
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        log_level=args.log_level,
        working_dir=args.working_dir,
        workflow_timeout=args.workflow_timeout,
    )

    # Create and start the worker
    worker = IssueWorker(config)
    worker.run()
