"""
Update get_and_lock_next_issue to mark issues as started when locked.
"""

from yoyo import step

__depends__ = {"008_restore_lock_rpc"}

step(
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        WITH next_issue AS (
            SELECT i.id
            FROM issues i
            WHERE i.type IN ('main', 'patch')
              AND i.status = 'pending'
              AND i.assigned_to = p_worker_id
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
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT i.id, i.description, i.status, i.type
        FROM issues i
        WHERE i.type IN ('main', 'patch')
          AND i.status = 'pending'
          AND i.assigned_to = p_worker_id
        ORDER BY i.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END;
    $$;
    """,
)
