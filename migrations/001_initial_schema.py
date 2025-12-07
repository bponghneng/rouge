"""
Initial schema migration for Rouge.

Creates the issues and comments tables with all columns,
worker_id enum type, indexes, triggers, and the get_and_lock_next_issue function.
"""

from yoyo import step

__depends__ = {}

# Create worker_id enum type with all 12 worker values
step(
    """
    CREATE TYPE worker_id AS ENUM (
        'alleycat-1',
        'alleycat-2',
        'alleycat-3',
        'hailmary-1',
        'hailmary-2',
        'hailmary-3',
        'local-1',
        'local-2',
        'local-3',
        'tydirium-1',
        'tydirium-2',
        'tydirium-3'
    );
    """,
    "DROP TYPE IF EXISTS worker_id;",
)

# Create issues table with all columns
step(
    """
    CREATE TABLE IF NOT EXISTS issues (
        id SERIAL PRIMARY KEY,
        title TEXT,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'started', 'completed')),
        assigned_to worker_id,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    """,
    "DROP TABLE IF EXISTS issues CASCADE;",
)

# Create comments table with all columns
step(
    """
    CREATE TABLE IF NOT EXISTS comments (
        id SERIAL PRIMARY KEY,
        issue_id INT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
        comment TEXT NOT NULL,
        raw JSONB NOT NULL DEFAULT '{}'::jsonb,
        source TEXT,
        type TEXT,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """,
    "DROP TABLE IF EXISTS comments CASCADE;",
)

# Create indexes for performance
step(
    """
    CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
    """,
    "DROP INDEX IF EXISTS idx_issues_status;",
)

step(
    """
    CREATE INDEX IF NOT EXISTS idx_issues_assigned_to ON issues(assigned_to);
    """,
    "DROP INDEX IF EXISTS idx_issues_assigned_to;",
)

step(
    """
    CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON comments(issue_id);
    """,
    "DROP INDEX IF EXISTS idx_comments_issue_id;",
)

# Create updated_at trigger function
step(
    """
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """,
    "DROP FUNCTION IF EXISTS update_updated_at_column();",
)

# Create trigger on issues table
step(
    """
    CREATE TRIGGER update_issues_updated_at
    BEFORE UPDATE ON issues
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """,
    "DROP TRIGGER IF EXISTS update_issues_updated_at ON issues;",
)

# Create get_and_lock_next_issue function
step(
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
    RETURNS TABLE (issue_id INTEGER, issue_description TEXT) AS $$
    BEGIN
        RETURN QUERY
        UPDATE issues
        SET status = 'started',
            assigned_to = p_worker_id,
            updated_at = now()
        WHERE issues.id = (
            SELECT id
            FROM issues
            WHERE status = 'pending'
              AND assigned_to = p_worker_id
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING issues.id, issues.description;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP FUNCTION IF EXISTS get_and_lock_next_issue(worker_id);",
)
