-- Fix migration 003_add_patches_table.py
-- Run this in the Supabase Dashboard SQL Editor

-- 1. Create patches table
CREATE TABLE IF NOT EXISTS patches (
    id SERIAL PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Indexes
CREATE INDEX IF NOT EXISTS idx_patches_issue_id ON patches(issue_id);
CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patches_one_per_issue ON patches(issue_id);

-- 3. Update issue status check constraint
ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_status_check;
ALTER TABLE issues ADD CONSTRAINT issues_status_check
    CHECK (status IN ('pending', 'started', 'completed', 'patch pending', 'patched'));

-- 4. Trigger function for patches
CREATE OR REPLACE FUNCTION check_patch_issue_status()
RETURNS TRIGGER AS $$
DECLARE
    current_status TEXT;
BEGIN
    SELECT status INTO current_status FROM issues WHERE id = NEW.issue_id;
    
    -- ALLOW 'patch pending' and 'started' because the worker updates the issue to 'started' while working on a patch
    IF current_status NOT IN ('completed', 'patched', 'patch pending', 'started') THEN
        RAISE EXCEPTION 'Patches can only be created/updated for issues with status completed, patched, patch pending, or started. Issue % has status %', 
            NEW.issue_id, current_status;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS patches_issue_status_check ON patches;
CREATE TRIGGER patches_issue_status_check
BEFORE INSERT OR UPDATE ON patches
FOR EACH ROW EXECUTE FUNCTION check_patch_issue_status();

-- 5. Trigger for updated_at on patches
DROP TRIGGER IF EXISTS update_patches_updated_at ON patches;
CREATE TRIGGER update_patches_updated_at
BEFORE UPDATE ON patches
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 6. Corrected get_and_lock_next_issue function
CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_issue_id INT;
    v_description TEXT;
    v_old_status TEXT;
BEGIN
    -- Find the issue
    SELECT id, description, status
    INTO v_issue_id, v_description, v_old_status
    FROM issues
    WHERE status IN ('pending', 'patch pending')
      AND assigned_to = p_worker_id
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    -- If found, update it to started so it's locked
    IF v_issue_id IS NOT NULL THEN
        UPDATE issues
        SET status = 'started',
            updated_at = now()
        WHERE id = v_issue_id;
        
        -- Return the ORIGINAL status so the worker knows if it's a patch or new issue
        RETURN QUERY SELECT v_issue_id, v_description, v_old_status;
    END IF;
END;
$$;
