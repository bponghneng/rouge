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
- `get_and_lock_next_issue(worker_id)` - Atomic issue locking for worker processing

### Enum Types
- `worker_id` - Valid worker identifiers (alleycat-1/2/3, executor-1/2/3, hailmary-1/2/3, local-1/2/3, tydirium-1/2/3, xwing-1/2/3)
