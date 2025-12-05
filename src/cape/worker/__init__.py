"""Cape Worker Package

This package provides the issue worker functionality for the Cape system.
"""

from .cli import main
from .config import WorkerConfig
from .database import get_client, get_next_issue, update_issue_status
from .worker import IssueWorker

__all__ = [
    "IssueWorker",
    "get_client",
    "get_next_issue",
    "update_issue_status",
    "WorkerConfig",
    "main",
]
