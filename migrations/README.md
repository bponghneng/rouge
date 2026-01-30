# Database Migrations

This project uses [yoyo-migrations](https://ollycope.com/software/yoyo/latest/) for database schema management.

## Prerequisites

- PostgreSQL database (e.g., Supabase, local Postgres)
- Database password for your Supabase project

## Running Migrations

### Apply Migrations

```bash
# Set DATABASE_URL inline and apply migrations
DATABASE_URL='postgresql://postgres.[SUPABASE_PROJECT]:[DATABASE_PASSWORD]@aws-0-us-west-2.pooler.supabase.com:5432/postgres' && uv run yoyo apply --database "$DATABASE_URL"
```

### Rollback Migrations

```bash
# Roll back the most recent migration
DATABASE_URL='postgresql://postgres.[SUPABASE_PROJECT]:[DATABASE_PASSWORD]@aws-0-us-west-2.pooler.supabase.com:5432/postgres' && uv run yoyo rollback --database "$DATABASE_URL"
```

### Show Migration Status

```bash
DATABASE_URL='postgresql://postgres.[SUPABASE_PROJECT]:[DATABASE_PASSWORD]@aws-0-us-west-2.pooler.supabase.com:5432/postgres' && uv run yoyo show --database "$DATABASE_URL"
```

## Configuration

The `yoyo.ini` file in the project root configures the migrations directory:

```ini
[DEFAULT]
sources = migrations/
migration_table = _yoyo_migration
batch_mode = on
```

## Verification

After running migrations, verify tables exist:

```sql
SELECT * FROM issues;
SELECT * FROM comments;
```

## Schema Overview

The initial migration (`001_initial_schema.py`) creates:

### Tables
- `issues` - Main issue tracking table with status, assignment, and timestamps
- `comments` - Comments on issues with JSONB raw field for metadata

### Indexes
- `idx_issues_status` - For efficient status filtering
- `idx_issues_assigned_to` - For worker assignment queries
- `idx_comments_issue_id` - For fetching comments by issue

### Functions
- `update_updated_at_column()` - Trigger function for automatic timestamp updates
- `get_and_lock_next_issue()` - Atomically finds and locks the next available issue (no worker filter)
- `get_and_lock_next_issue(worker_id)` - Atomically finds and locks the next available issue for a specific worker

Note: The lock RPC was removed in `006_remove_lock_rpc.py` but restored in
`008_restore_lock_rpc.py` to prevent race conditions when multiple workers
poll concurrently. The RPC provides atomic SELECT-and-UPDATE to ensure no
two workers can claim the same issue.

### Enum Types
- `worker_id` - Valid worker identifiers (alleycat-1/2/3, executor-1/2/3, hailmary-1/2/3, local-1/2/3, tydirium-1/2/3, xwing-1/2/3)
