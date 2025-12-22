"""
Add adw_id column to comments table.

Adds a nullable TEXT column to track runtime-generated ADW (Agent Development Workflow) UUIDs
associated with comments. This enables linking comments to specific workflow executions without
requiring a foreign key constraint since ADW IDs are generated at runtime.
"""

from yoyo import step

__depends__ = {"001_initial_schema"}

# Add adw_id column to comments table
step(
    """
    ALTER TABLE comments ADD COLUMN adw_id TEXT;
    """,
    "ALTER TABLE comments DROP COLUMN adw_id;",
)
