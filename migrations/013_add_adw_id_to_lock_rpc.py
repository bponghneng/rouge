"""
Add adw_id to the get_and_lock_next_issue RPC return type.

This migration extends the get_and_lock_next_issue function to also return
the issue's adw_id field, enabling callers to access the ADW identifier
without a separate query.
"""

from yoyo import step

__depends__ = {"012_assigned_to_free_text"}

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
            WHERE i.type IN ('main', 'patch', 'codereview')
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
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        WITH next_issue AS (
            SELECT i.id
            FROM issues i
            WHERE i.type IN ('main', 'patch', 'codereview')
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
        RETURNING i.id, i.description, i.status, i.type;
    END;
    $$;
    """,
)
