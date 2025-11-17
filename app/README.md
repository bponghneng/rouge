# CAPE Application Suite

## Overview

The `cape/app` package is the installable bundle for CAPE’s workflow automation
stack. It combines the Textual-based TUI, Typer CLIs, and the automated worker
daemon on top of a shared `cape.core` foundation (Supabase models, workflow
orchestration, logging utilities). Use it to create issues, generate plans,
launch Claude-based implementations, or run unattended workers against Supabase.

## Components

- `cape.cli` – Typer CLI with a Textual TUI (`uv run cape`) plus subcommands for
  creating issues, launching workflows, tailing logs, and managing background
  processes.
- `cape.adw` – Lightweight CLI (`uv run cape-adw`) that executes the Agent
  Development Workflow (fetch → classify → plan → implement) for a single issue.
- `cape.worker` – Long-running daemon (`uv run cape-worker --worker-id …`) that
  polls Supabase, atomically locks the next pending issue, and shells out to the
  ADW CLI so multiple hosts can process the queue without collisions.
- `cape.core` – Shared Supabase client, pydantic models, workflow orchestration,
  and logging utilities used by every entry point.

## Quick Start

```bash
cd cape/app
uv sync

# Launch the interactive TUI
uv run cape

# Execute a workflow from the CLI
uv run cape run 123
uv run cape run 123 --working-dir "C:\Users\bpong\git\cape"

# Run the headless ADW command
uv run cape-adw 123

# Start a background worker
uv run cape-worker --worker-id alleycat-1
uv run cape-worker --worker-id alleycat-1 --working-dir "C:\Users\bpong\git\cape"
```

> **Note:** The worker shells out to `uv run cape-adw`. If you execute the worker
> outside of the `cape/app` directory, set `CAPE_APP_ROOT=/absolute/path/to/cape/app`
> so it knows where to run the workflow command. Combine this with the
> `--working-dir` flag if you want the worker process itself to `chdir` elsewhere.

## Environment & Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `SUPABASE_URL` | ✅ | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service role key used by the CLI/worker. |
| `ANTHROPIC_API_KEY` | ✅ for workflow execution | Allows the workflow to call Claude via the local CLI. |
| `CAPE_AGENTS_DIR` | optional | Override for `.cape/logs/agents` directory. |
| `CAPE_DATA_DIR` / `CAPE_RUNTIME_DIR` | optional | Custom storage locations for PID/state/log files. |
| `CAPE_APP_ROOT` | optional | Root directory the worker uses when launching `uv run cape-adw`. |

Create a `.env` or set the variables in your shell before running the tools.

## Worker Installation & Operation

### Manual Run

```bash
cd cape/app
uv run cape-worker --worker-id alleycat-1 \
  --poll-interval 10 \
  --log-level INFO
```

You can also invoke the package directly once it is installed:

```bash
python -m cape.worker --worker-id alleycat-1 [--poll-interval 5] [--log-level DEBUG]
```

Required flag:

- `--worker-id` – human-friendly identifier (e.g., `alleycat-1`, `tydirium-1`).

Optional flags:

- `--poll-interval` – seconds between Supabase polls (default `10`).
- `--log-level` – `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default `INFO`).
- `--working-dir` – absolute directory to switch into before polling (default: current directory).

### System Service (Linux / systemd)

Service templates live in `app/ops/daemons/worker/`. To install:

```bash
# copy and customize the template (set CAPE_APP_ROOT, worker id, etc.)
sudo cp app/ops/daemons/worker/cape-worker.service \
  /etc/systemd/system/cape-worker-alleycat-1.service
sudo systemctl daemon-reload
sudo systemctl enable cape-worker-alleycat-1.service
sudo systemctl start cape-worker-alleycat-1.service

# helpful commands
sudo systemctl status cape-worker-alleycat-1.service
sudo journalctl -u cape-worker-alleycat-1.service -f
```

### System Service (macOS / launchd)

```bash
cp app/ops/daemons/worker/com.cape.worker.plist \
  ~/Library/LaunchAgents/com.cape.worker.alleycat-1.plist
launchctl load ~/Library/LaunchAgents/com.cape.worker.alleycat-1.plist
launchctl start com.cape.worker.alleycat-1

# manage service
launchctl stop com.cape.worker.alleycat-1
launchctl list | grep com.cape.worker
launchctl unload ~/Library/LaunchAgents/com.cape.worker.alleycat-1.plist
```

Both service definitions assume `uv` is on the PATH, `CAPE_APP_ROOT` points to
`/absolute/path/to/cape/app`, and the `.env` contains Supabase + Anthropic creds.

## TUI Highlights

- **Issue List View** – browse the Supabase backlog with ID, description,
  status, and created timestamp.
- **Issue Detail** – view metadata and comments with auto-refresh timer that
  keeps "started" issues up to date.
- **Keyboard shortcuts** – `n` (new issue), `Enter`/`v` (details), `d` (delete
  pending issue), `q` (quit), `?` (help), `Ctrl+S` (save forms), `Esc` (close
  modal).

The TUI runs from the same executable (`uv run cape`) and uses `cape.core`
internals, so no duplicate configuration is required.

Workflows can be executed directly using:
- `cape run <issue-id>` - Execute workflow synchronously in foreground
- `cape create "description"` - Create a new issue from description string
- `cape create-from-file <file>` - Create a new issue from description file

For asynchronous workflow processing, use the worker daemon (see Worker Features below).

## Worker Features

- Polls `cape_issues` for `status='pending'`, locks the next row via a
  PostgreSQL function, and marks it `started` while recording the `worker_id`.
- Spawns `uv run cape-adw <issue-id> --adw-id <workflow-id>` with clear logging
  so you can tail progress from the TUI or by reading log files directly.
- Supports multiple concurrent instances (systemd service files live in
  `app/ops/daemons/worker/` for Linux and launchd plists for macOS).
- Logs to `.cape/logs/agents/{workflow_id}/adw_plan_build/execution.log` for
  tracking workflow progress.

Example service install scripts for systemd/launchd are in `app/ops/daemons/`.

## Database Requirements

All executables expect the standard Supabase schema plus the worker RPC defined
in `cape/migrations/003_add_worker_assignment.sql`. Key pieces:

```sql
CREATE TYPE worker_id AS ENUM ('alleycat-1', 'tydirium-1');

ALTER TABLE cape_issues
ADD COLUMN assigned_to worker_id;

CREATE OR REPLACE FUNCTION get_and_lock_next_issue(p_worker_id worker_id)
RETURNS TABLE (issue_id INTEGER, issue_description TEXT) AS $$
BEGIN
    RETURN QUERY
    UPDATE cape_issues
    SET status = 'started', assigned_to = p_worker_id, updated_at = now()
    WHERE id = (
        SELECT id FROM cape_issues
        WHERE status = 'pending'
          AND assigned_to = p_worker_id
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING cape_issues.id, cape_issues.description;
END;
$$ LANGUAGE plpgsql;
```

Run that migration (or apply equivalent DDL) before starting the worker so each
instance can atomically claim work.

## Tests

```bash
cd cape/app
uv run pytest tests/ -v
```

## Project Layout

```
app/
├── pyproject.toml        # unified build configuration
├── src/cape/             # Python packages (core, cli, adw, worker)
└── tests/                # consolidated unit tests
```

Service templates and installation helpers for the worker live under
`app/ops/daemons`.

For the broader methodology, specs, and AI-agent prompts, see the workspace
README (`../README.md`) and the historical context in
`cape.worktrees/add-worker/README.md`.

