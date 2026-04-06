"""
Migration 017: Add 'claimed' issue status.

Widens the schema so 'claimed' is a valid issue status alongside
'pending', 'started', 'completed', and 'failed'.

Changes:
  1. Replace the CHECK constraint on issues.status to allow 'claimed'.
  2. Recreate get_and_lock_next_issue RPC to transition pending -> claimed.

Rollback reverts both changes to the 4-status constraint and started-based RPC.
"""

from yoyo import step

__depends__ = {"016_add_thin_type"}

step(
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'claimed', 'started', 'completed', 'failed'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'started', 'completed', 'failed'));
    """,
)

step(
    """
    DROP FUNCTION IF EXISTS get_and_lock_next_issue(TEXT);
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id TEXT)
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT, issue_adw_id TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        WITH next_issue AS (
            SELECT i.id
            FROM issues i
            WHERE i.type IN ('direct','full', 'patch', 'thin')
              AND i.status = 'pending'
              AND i.assigned_to::TEXT = p_worker_id
            ORDER BY i.id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE issues i
        SET status = 'claimed'
        FROM next_issue
        WHERE i.id = next_issue.id
        RETURNING i.id, i.description, i.status, i.type, i.adw_id;
    END;
    $$;
    """,
    """
    DROP FUNCTION IF EXISTS get_and_lock_next_issue(TEXT);
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id TEXT)
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT, issue_adw_id TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        WITH next_issue AS (
            SELECT i.id
            FROM issues i
            WHERE i.type IN ('direct','full', 'patch', 'thin')
              AND i.status = 'pending'
              AND i.assigned_to::TEXT = p_worker_id
            ORDER BY i.id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE issues i
        SET status = 'started'
        FROM next_issue
        WHERE i.id = next_issue.id
        RETURNING i.id, i.description, i.status, i.type, i.adw_id;
    END;
    $$;
    """,
)
