"""
Migration 015: Remove 'main' workflow/issue type.

Deletes all existing 'main' issues, then tightens the schema so
only 'full' and 'patch' are valid issue types going forward.

Changes:
  1. DELETE all rows with type='main' (irreversible).
  2. Replace the CHECK constraint on issues.type to allow only ('full', 'patch').
  3. Recreate get_and_lock_next_issue RPC to filter on ('full', 'patch') only.

The rollback steps restore the 'main' type in the constraint and RPC, but
cannot restore deleted rows.
"""

from yoyo import step

__depends__ = {"014_remove_codereview_type"}

step(
    """
    DELETE FROM issues WHERE type = 'main';
    """
)

step(
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('full', 'patch'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('main', 'full', 'patch'));
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
            WHERE i.type IN ('full', 'patch')
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
            WHERE i.type IN ('main', 'patch')
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
