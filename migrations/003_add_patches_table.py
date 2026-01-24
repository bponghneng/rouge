"""
Add patches table and extend issues status constraint.

Creates the patches table to track patch records associated with issues,
including indexes for efficient querying and an updated_at trigger.
Also extends the issues table status constraint to include patch-related statuses.
"""

from yoyo import step

__depends__ = {"002_add_adw_id_to_comments"}

# Create patches table
step(
    """
    CREATE TABLE IF NOT EXISTS patches (
        id SERIAL PRIMARY KEY,
        issue_id INT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
        description TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    """,
    "DROP TABLE IF EXISTS patches CASCADE;",
)

# Create index on issue_id for efficient lookups
step(
    """
    CREATE INDEX IF NOT EXISTS idx_patches_issue_id ON patches(issue_id);
    """,
    "DROP INDEX IF EXISTS idx_patches_issue_id;",
)

# Create index on status for efficient filtering
step(
    """
    CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);
    """,
    "DROP INDEX IF EXISTS idx_patches_status;",
)

# Create unique index to enforce only one patch per issue
step(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_patches_one_per_issue ON patches(issue_id);
    """,
    "DROP INDEX IF EXISTS idx_patches_one_per_issue;",
)

# Add check constraint to enforce patches can only be created when issue is 'completed' or 'patched'
# This uses a function to validate the issue status at insert/update time
step(
    """
    CREATE OR REPLACE FUNCTION check_patch_issue_status()
    RETURNS TRIGGER AS $$
    DECLARE
        current_status TEXT;
    BEGIN
        SELECT status INTO current_status FROM issues WHERE id = NEW.issue_id;

        IF current_status NOT IN ('completed', 'patched') THEN
            RAISE EXCEPTION 'Patches can only be created for issues with status completed or patched, but issue % has status %',
                NEW.issue_id, current_status;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER patches_issue_status_check
    BEFORE INSERT OR UPDATE ON patches
    FOR EACH ROW EXECUTE FUNCTION check_patch_issue_status();
    """,
    """
    DROP TRIGGER IF EXISTS patches_issue_status_check ON patches;
    DROP FUNCTION IF EXISTS check_patch_issue_status();
    """,
)

# Create trigger for updated_at on patches table
step(
    """
    CREATE TRIGGER update_patches_updated_at
    BEFORE UPDATE ON patches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """,
    "DROP TRIGGER IF EXISTS update_patches_updated_at ON patches;",
)

# Alter issues table status constraint to include patch-related statuses
step(
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'started', 'completed', 'patch pending', 'patched'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
    ALTER TABLE issues ADD CONSTRAINT issues_status_check
        CHECK (status IN ('pending', 'started', 'completed'));
    """,
)

# Update get_and_lock_next_issue function to support patch workflow
step(
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue()
    RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT i.id, i.description, i.status
        FROM issues i
        WHERE i.status = 'pending' OR i.status = 'patch pending'
        ORDER BY i.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END;
    $$;
    """,
    """
    CREATE OR REPLACE FUNCTION get_and_lock_next_issue()
    RETURNS TABLE(issue_id INT, issue_description TEXT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT i.id, i.description
        FROM issues i
        WHERE i.status = 'pending'
        ORDER BY i.id
        FOR UPDATE SKIP LOCKED
        LIMIT 1;
    END;
    $$;
    """,
)
