"""
Remove 'codereview' issue type.

Deletes existing codereview rows, tightens the CHECK constraint on
issues.type to only allow 'main' and 'patch', and recreates the
get_and_lock_next_issue RPC without codereview in the WHERE clause.
"""

from yoyo import step

__depends__ = {"013_add_adw_id_to_lock_rpc"}

# IRREVERSIBLE: permanently deletes all codereview issues.
# Ensure any needed codereview issues are exported or resolved before applying.
step(
    """
    DELETE FROM issues WHERE type = 'codereview';
    """,
)

step(
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('main', 'patch'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('main', 'patch', 'codereview'));
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
)
