"""Command-line interface for the Rouge Worker."""

import argparse
import os
import sys

from .config import WorkerConfig
from .worker import IssueWorker


def main():
    """Parse command line arguments and start the worker."""
    # Safely parse ROUGE_WORKFLOW_TIMEOUT_SECONDS env var
    default_timeout = 3600
    timeout_env = os.environ.get("ROUGE_WORKFLOW_TIMEOUT_SECONDS")
    if timeout_env:
        try:
            parsed_timeout = int(timeout_env)
            if parsed_timeout <= 0:
                print(
                    f"Warning: ROUGE_WORKFLOW_TIMEOUT_SECONDS must be positive, "
                    f"got '{timeout_env}', using default {default_timeout} seconds",
                    file=sys.stderr,
                )
            else:
                default_timeout = parsed_timeout
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

    default_log_level = os.environ.get("ROUGE_LOG_LEVEL", "INFO").upper()
    if default_log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        default_log_level = "INFO"

    parser.add_argument(
        "--log-level",
        default=default_log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=f"Logging level (default: {default_log_level})",
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
        workflow_timeout=args.workflow_timeout,
    )

    # Create and start the worker
    worker = IssueWorker(config)
    worker.run()
