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
