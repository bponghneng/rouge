"""
Allow issues.adw_id to be nullable.

Drops the NOT NULL constraint on issues.adw_id. Rollback backfills any NULLs
to avoid constraint violations, then re-applies NOT NULL.
"""

from yoyo import step

__depends__ = {"006_remove_lock_rpc"}

# Forward migration: drop NOT NULL constraint
# Rollback: re-apply NOT NULL constraint (runs second during rollback)
step(
    """
    ALTER TABLE issues ALTER COLUMN adw_id DROP NOT NULL;
    """,
    """
    ALTER TABLE issues ALTER COLUMN adw_id SET NOT NULL;
    """,
)

# Rollback: backfill NULLs before re-applying NOT NULL (runs first during rollback)
# Note: The issues table is expected to remain small (< 10k rows). If the table
# grows significantly, consider implementing batched updates to avoid long locks.
step(
    None,  # No forward action for this step
    """
    UPDATE issues
    SET adw_id = substring(REPLACE(gen_random_uuid()::text, '-', '') FROM 1 FOR 8)
    WHERE adw_id IS NULL;
    """,
)
