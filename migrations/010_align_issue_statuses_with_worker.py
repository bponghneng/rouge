"""
Align issues.status constraint with worker-supported statuses.

Normalizes deprecated legacy statuses to the current canonical set and updates
issues_status_check to allow only: pending, started, completed, failed.
"""

from yoyo import step

__depends__ = {"009_lock_issue_sets_started"}

step(
    """
    UPDATE issues
    SET status = CASE
        WHEN status = 'patch pending' THEN 'pending'
        WHEN status = 'patched' THEN 'completed'
        ELSE status
    END
    WHERE status IN ('patch pending', 'patched');

    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'started', 'completed', 'failed'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'started', 'completed', 'failed', 'patch pending', 'patched'));
    """,
)
