"""Command-line interface for the Cape Worker."""

import argparse
from pathlib import Path

from .config import WorkerConfig
from .worker import IssueWorker


def main():
    """Parse command line arguments and start the worker."""
    parser = argparse.ArgumentParser(
        description="CAPE Issue Worker Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cape-worker --worker-id alleycat-1
  python -m cape-worker --worker-id tydirium-1 --poll-interval 5 --log-level DEBUG
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

    args = parser.parse_args()

    # Create configuration
    config = WorkerConfig(
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        log_level=args.log_level,
        working_dir=args.working_dir,
    )

    # Create and start the worker
    worker = IssueWorker(config)
    worker.run()
