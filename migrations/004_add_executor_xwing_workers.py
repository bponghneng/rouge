"""
Add executor and xwing worker IDs to the worker_id enum.

Extends the worker_id enum type with six new values:
executor-1, executor-2, executor-3, xwing-1, xwing-2, xwing-3

Note: PostgreSQL does not support removing enum values directly. The rollback
step logs a warning instead of attempting to remove the values, as this would
require recreating the enum type and all dependent objects.
"""

from yoyo import step

__depends__ = {"003_add_patches_table"}

# Add executor worker IDs to the worker_id enum
step(
    """
    ALTER TYPE worker_id ADD VALUE 'executor-1';
    """,
    """
    -- PostgreSQL does not support removing enum values directly.
    -- To remove this value, the enum type would need to be recreated
    -- along with all dependent columns, constraints, and functions.
    -- Manual intervention required for rollback.
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value executor-1 - manual intervention required'; END $$;
    """,
)

step(
    """
    ALTER TYPE worker_id ADD VALUE 'executor-2';
    """,
    """
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value executor-2 - manual intervention required'; END $$;
    """,
)

step(
    """
    ALTER TYPE worker_id ADD VALUE 'executor-3';
    """,
    """
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value executor-3 - manual intervention required'; END $$;
    """,
)

# Add xwing worker IDs to the worker_id enum
step(
    """
    ALTER TYPE worker_id ADD VALUE 'xwing-1';
    """,
    """
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value xwing-1 - manual intervention required'; END $$;
    """,
)

step(
    """
    ALTER TYPE worker_id ADD VALUE 'xwing-2';
    """,
    """
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value xwing-2 - manual intervention required'; END $$;
    """,
)

step(
    """
    ALTER TYPE worker_id ADD VALUE 'xwing-3';
    """,
    """
    DO $$ BEGIN RAISE WARNING 'Cannot remove enum value xwing-3 - manual intervention required'; END $$;
    """,
)
