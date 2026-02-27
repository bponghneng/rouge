"""
Convert assigned_to column from worker_id enum to TEXT for flexible assignment.

This migration removes the dependency on the worker_id enum type by converting
the assigned_to column to TEXT, enabling assignment to any arbitrary identifier
(worker IDs, user emails, agent names, etc.) while maintaining backward
compatibility with existing worker_id values.

The get_and_lock_next_issue function is updated to accept TEXT instead of worker_id.
"""

from yoyo import step

__depends__ = {"011_add_codereview_issue_type"}

# Update get_and_lock_next_issue function to accept TEXT parameter before column conversion
step(
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id TEXT)
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
)

# Convert assigned_to column from worker_id enum to TEXT
step(
    """
    ALTER TABLE issues ALTER COLUMN assigned_to TYPE TEXT USING assigned_to::TEXT;
    """,
    """
    ALTER TABLE issues ALTER COLUMN assigned_to TYPE worker_id USING assigned_to::worker_id;
    """,
)
