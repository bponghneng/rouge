"""
Remove get_and_lock_next_issue RPC functions.

This migration drops both the parameterized and no-arg function signatures
used for worker issue locking. Rollback restores both signatures.
"""

from yoyo import step

__depends__ = {"005_refactor_patches_to_issues"}

step(
    """
    DROP FUNCTION IF EXISTS get_and_lock_next_issue(worker_id);
    DROP FUNCTION IF EXISTS get_and_lock_next_issue();
    """,
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue()
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT i.id, i.description, i.status, i.type
        FROM issues i
        WHERE i.type IN ('main', 'patch')
          AND (i.status = 'pending' OR i.status = 'patch pending')
        ORDER BY i.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END;
    $$;

    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT i.id, i.description, i.status, i.type
        FROM issues i
        WHERE i.type IN ('main', 'patch')
          AND (i.status = 'pending' OR i.status = 'patch pending')
          AND i.assigned_to = p_worker_id
        ORDER BY i.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END;
    $$;
    """,
)
