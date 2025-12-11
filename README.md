# Rouge Application Suite

## Overview

The `rouge/` package is the installable bundle for Rouge's workflow automation
stack. It combines Typer CLIs and the automated worker daemon on top of a shared
`rouge.core` foundation (Supabase models, workflow orchestration, logging
utilities). Use it to create issues, generate plans, launch Claude-based
implementations, or run unattended workers against Supabase.

## Components

- `rouge.cli` – Typer CLI (`uv run rouge`) with subcommands for creating issues,
  launching workflows, and managing background processes.
- `rouge.adw` – Lightweight CLI (`uv run rouge-adw`) that executes the Agent
  Development Workflow (fetch → classify → plan → implement) for a single issue.
- `rouge.worker` – Long-running daemon (`uv run rouge-worker --worker-id …`) that
  polls Supabase, atomically locks the next pending issue, and shells out to the
  ADW CLI so multiple hosts can process the queue without collisions.
- `rouge.core` – Shared Supabase client, pydantic models, workflow orchestration,
  and logging utilities used by every entry point.

## Quick Start

```bash
cd rouge
uv sync

# Show CLI help
uv run rouge --help

# Execute a workflow from the CLI
uv run rouge run 123
uv run rouge run 123 --working-dir "C:\Users\bpong\git\rouge"

# Run the headless ADW command
uv run rouge-adw 123

# Start a background worker
uv run rouge-worker --worker-id alleycat-1
uv run rouge-worker --worker-id alleycat-1 --working-dir "C:\Users\bpong\git\rouge"
```

> **Note:** The worker shells out to `uv run rouge-adw`. If you execute the worker
> outside of the `rouge/` directory, set `ROUGE_APP_ROOT=/absolute/path/to/rouge`
> so it knows where to run the workflow command. Combine this with the
> `--working-dir` flag if you want the worker process itself to `chdir` elsewhere.

## Environment & Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `SUPABASE_URL` | ✅ | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service role key used by the CLI/worker. |
| `ANTHROPIC_API_KEY` | ✅ for workflow execution | Allows the workflow to call Claude via the local CLI. |
| `ROUGE_IMPLEMENT_PROVIDER` | optional | Provider for `/implement` step: `"claude"` (default) or `"opencode"`. |
| `ROUGE_AGENTS_DIR` | optional | Override for `.rouge/logs/agents` directory. |
| `ROUGE_DATA_DIR` / `ROUGE_RUNTIME_DIR` | optional | Custom storage locations for PID/state/log files. |
| `ROUGE_APP_ROOT` | optional | Root directory the worker uses when launching `uv run rouge-adw`. |
| `ROUGE_ADW_COMMAND` | optional | Override command to run rouge-adw (e.g. `uv run rouge-adw`). |
| `OPENCODE_PATH` | optional | Path to OpenCode CLI (defaults to `"opencode"`). |
| `OPENCODE_API_KEY` | optional | API key for OpenCode provider. |
| `GITHUB_PAT` | optional | Personal access token for GitHub (repo scope). Required for automatic PR creation. Requires `gh` CLI. |
| `GITLAB_PAT` | optional | Personal access token for GitLab (api scope). Required for automatic MR creation when `DEV_SEC_OPS_PLATFORM=gitlab`. Requires `glab` CLI. |
| `DEV_SEC_OPS_PLATFORM` | optional | Platform for PR/MR creation: `"github"` or `"gitlab"`. If not set, PR/MR creation step is skipped. |

Create a `.env` file in the directory where you are running the `rouge` commands from, or set the variables directly in your shell environment.

### Provider Configuration

Rouge supports multiple AI coding agent providers for the implementation step. By default, all workflow steps (classification, planning, and implementation) use Claude Code. You can configure a different provider for the implementation step using the `ROUGE_IMPLEMENT_PROVIDER` environment variable.

**Default behavior (Claude for all steps):**
```bash
# No configuration needed - Claude is the default
uv run rouge-adw 123
```

**Using OpenCode for implementation:**
```bash
# Install OpenCode CLI first
npm install -g @opencode/cli

# Configure environment
export ROUGE_IMPLEMENT_PROVIDER=opencode
export OPENCODE_API_KEY=your-opencode-api-key

# Run workflow - classification and planning use Claude, implementation uses OpenCode
uv run rouge-adw 123
```

**Provider selection priority:**
1. `ROUGE_IMPLEMENT_PROVIDER` - Most specific, controls only the implementation step
2. `ROUGE_AGENT_PROVIDER` - Fallback for general provider selection
3. Default: `"claude"` if neither is set

**Supported providers:**
- `claude` - Claude Code CLI (default, requires `ANTHROPIC_API_KEY`)
- `opencode` - OpenCode CLI (requires `OPENCODE_API_KEY`)

## Worker Installation & Operation

The `rouge-worker` daemon is designed to run in the background, processing issues from Supabase. It can be installed globally or run from the project directory.

### Global Installation

To install `rouge` and its CLI commands globally using `uv tool`, making `rouge-worker` available from any directory:

```bash
cd rouge
uv tool install .
```
*   **Note:** If you update the `rouge` package source, run `uv tool upgrade rouge` to apply the changes to your global installation.

### Manual Run (Local or Global)

You can run the worker directly. If installed globally, omit `uv run`.

**From project directory (development):**
```bash
cd rouge
uv run rouge-worker --worker-id alleycat-1 \
  --poll-interval 10 \
  --log-level INFO \
  --working-dir "/path/to/process/issues/in" # Optional, if different from current dir
```

**After global installation:**
```bash
rouge-worker --worker-id alleycat-1 \
  --poll-interval 10 \
  --log-level INFO \
  --working-dir "/path/to/process/issues/in" # Optional, if different from current dir
```

Required flag:

- `--worker-id` – human-friendly identifier (e.g., `alleycat-1`, `tydirium-1`).

Optional flags:

- `--poll-interval` – seconds between Supabase polls (default `10`).
- `--log-level` – `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default `INFO`).
- `--working-dir` – absolute directory to switch into before polling (default: current directory). This is where `rouge-adw` will execute its operations.

### Environment Variables for ADW Execution

The `rouge-worker` executes the `rouge-adw` command. You can control how `rouge-adw` is found and run using the following environment variables:

-   **`.env` file loading:** The worker attempts to load environment variables from a `.env` file. If `--working-dir` is specified, it will first look for `.env` in the directory specified by `--working-dir`, and then in its parent directory. If `--working-dir` is not specified, the worker will use the default behavior of searching for `.env` in the current directory and walking up the directory tree.
-   `ROUGE_APP_ROOT`: (Optional) Specifies the root directory of the `rouge` application. This is used as the `cwd` when spawning the `rouge-adw` command. It's crucial if `rouge-adw` isn't globally installed and the worker is run from outside the `rouge/` directory.
-   `ROUGE_ADW_COMMAND`: (Optional) Explicitly sets the command to execute for `rouge-adw` (e.g., `"/usr/local/bin/rouge-adw"` or `"uv run rouge-adw"`). If not set, the worker first checks if `rouge-adw` is in the system PATH, then falls back to `uv run rouge-adw`.

### System Service (Linux / systemd)

Service templates live in `ops/daemons/worker/`. To install:

```bash
# copy and customize the template (set ROUGE_APP_ROOT, worker id, etc.)
sudo cp ops/daemons/worker/rouge-worker.service \
  /etc/systemd/system/rouge-worker-alleycat-1.service
sudo systemctl daemon-reload
sudo systemctl enable rouge-worker-alleycat-1.service
sudo systemctl start rouge-worker-alleycat-1.service

# helpful commands
sudo systemctl status rouge-worker-alleycat-1.service
sudo journalctl -u rouge-worker-alleycat-1.service -f
```

### System Service (macOS / launchd)

```bash
cp ops/daemons/worker/com.rouge.worker.plist \
  ~/Library/LaunchAgents/com.rouge.worker.alleycat-1.plist
launchctl load ~/Library/LaunchAgents/com.rouge.worker.alleycat-1.plist
launchctl start com.rouge.worker.alleycat-1

# manage service
launchctl stop com.rouge.worker.alleycat-1
launchctl list | grep com.rouge.worker
launchctl unload ~/Library/LaunchAgents/com.rouge.worker.alleycat-1.plist
```

Both service definitions assume `uv` is on the PATH (for local development setups), `ROUGE_APP_ROOT` points to the absolute path to the `rouge` project, and the `.env` contains Supabase + Anthropic credentials.

## CLI Commands

Workflows can be executed directly using:
- `rouge run <issue-id>` - Execute workflow synchronously in foreground
- `rouge create "description"` - Create a new issue from description string
- `rouge create-from-file <file>` - Create a new issue from description file

For asynchronous workflow processing, use the worker daemon (see Worker Features below).

## Worker Features

- Polls `cape_issues` for `status='pending'`, locks the next row via a
  PostgreSQL function, and marks it `started` while recording the `worker_id`.
- Spawns `uv run rouge-adw <issue-id> --adw-id <workflow-id>` with clear logging
  so you can tail progress or read log files directly.
- Supports multiple concurrent instances (systemd service files live in
  `ops/daemons/worker/` for Linux and launchd plists for macOS).
- Logs to `.rouge/logs/agents/{workflow_id}/adw_plan_build/execution.log` for
  tracking workflow progress.

Example service install scripts for systemd/launchd are in `ops/daemons/`.

## Database Requirements

All executables expect the standard Supabase schema plus the worker RPC. Key pieces:

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
cd rouge
uv run pytest tests/ -v
```

## Project Layout

```
rouge/
├── pyproject.toml        # unified build configuration
├── src/rouge/            # Python packages (core, cli, adw, worker)
└── tests/                # consolidated unit tests
```

Service templates and installation helpers for the worker live under
`ops/daemons`.

For the broader methodology, specs, and AI-agent prompts, see the workspace
README (`../README.md`).
