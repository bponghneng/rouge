"""Entry point for running the Rouge Worker as a module.

This allows the worker to be executed using:
    python -m rouge.worker --worker-id <worker-id>
"""

from .cli import main

if __name__ == "__main__":
    main()
