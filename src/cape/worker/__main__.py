"""Entry point for running the Cape Worker as a module.

This allows the worker to be executed using:
    python -m cape-worker --worker-id <worker-id>
"""

from .cli import main

if __name__ == "__main__":
    main()
