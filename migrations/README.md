# Database Migrations

This project uses [yoyo-migrations](https://ollycope.com/software/yoyo/latest/) for database schema management.

## Prerequisites

- PostgreSQL database (e.g., Supabase, local Postgres)
- Environment variable `DATABASE_URL` set to your connection string

## Running Migrations

### Apply Migrations

```bash
# Using DATABASE_URL environment variable
yoyo apply --database "$DATABASE_URL"

# Or specify the database URL directly
yoyo apply --database postgresql://user:pass@host:port/dbname
```

### Rollback Migrations

```bash
# Roll back the most recent migration
yoyo rollback --database "$DATABASE_URL"
```

### Show Migration Status

```bash
yoyo show --database "$DATABASE_URL"
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
- `worker_id` - Valid worker identifiers (alleycat-1/2/3, hailmary-1/2/3, local-1/2/3, tydirium-1/2/3)
