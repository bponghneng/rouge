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

> **Note:** The worker shells out to `uv run rouge-adw`. Use the `--working-dir`
> flag to specify the directory where the worker should execute workflow operations.

## Environment & Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `SUPABASE_URL` | ✅ | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Service role key used by the CLI/worker. |
| `ANTHROPIC_API_KEY` | ✅ for workflow execution | Allows the workflow to call Claude via the local CLI. |
| `ROUGE_IMPLEMENT_PROVIDER` | optional | Provider for `/implement` step: `"claude"` (default) or `"opencode"`. |
| `ROUGE_AGENTS_DIR` | optional | Override for `.rouge/logs/agents` directory. |
| `ROUGE_DATA_DIR` / `ROUGE_RUNTIME_DIR` | optional | Custom storage locations for PID/state/log files. |
| `OPENCODE_PATH` | optional | Path to OpenCode CLI (defaults to `"opencode"`). |
| `OPENCODE_API_KEY` | optional | API key for OpenCode provider. |
| `GITHUB_PAT` | optional | Personal access token for GitHub (repo scope). Required for automatic PR creation. Requires `gh` CLI. |
| `GITLAB_PAT` | optional | Personal access token for GitLab (api scope). Required for automatic MR creation when `DEV_SEC_OPS_PLATFORM=gitlab`. Requires `glab` CLI. |
| `DEV_SEC_OPS_PLATFORM` | optional | Platform for PR/MR creation: `"github"` or `"gitlab"`. If not set, PR/MR creation step is skipped. |
| `ROUGE_WORKFLOW_TIMEOUT_SECONDS` | optional | Workflow execution timeout in seconds (default: 3600). |
| `CODERABBIT_TIMEOUT_SECONDS` | optional | Timeout for CodeRabbit review generation in seconds (default: 600). |

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

## Worker Operation

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
- `--workflow-timeout` – workflow execution timeout in seconds (default `3600`).

## CLI Commands

Workflows can be executed directly using:
- `rouge run <issue-id>` - Execute workflow synchronously in foreground
- `rouge create "description"` - Create a new issue from description string
- `rouge create-from-file <file>` - Create a new issue from description file

For asynchronous workflow processing, use the worker daemon (see Worker Features below).

## Artifact-Based Workflow

Rouge supports typed workflow artifacts that persist step inputs/outputs to disk.
Artifacts are stored under `~/.rouge/workflows/<workflow-id>/` by default, or
`$ROUGE_DATA_DIR/workflows/<workflow-id>/` when `ROUGE_DATA_DIR` is set.

Artifact-focused commands:

- `rouge step list` - List registered workflow steps and dependencies.
- `rouge step run <step-name> --issue-id <id> --adw-id <workflow-id>` - Run a single step using stored artifacts.
- `rouge step deps <step-name>` - Show dependency chain.
- `rouge step validate` - Validate step registry for missing producers or cycles.
- `rouge artifact list <workflow-id>` - List artifacts for a workflow.
- `rouge artifact show <workflow-id> <artifact-type>` - Display artifact JSON.
- `rouge artifact delete <workflow-id> <artifact-type>` - Remove a stored artifact.
- `rouge artifact types` - List available artifact types.
- `rouge artifact path <workflow-id>` - Show the artifact directory path.

Single-step execution requires artifacts from a prior run (or manually created
files in the workflow directory). Full workflow execution (`rouge run`,
`rouge-adw`, `rouge-worker`) always enables artifacts; use the step/artifact
commands to inspect or modify artifacts after a run.

If you run `rouge step run` outside the project directory, pass `--working-dir`
to load `.env` from that directory (or its parent), matching the worker's
`--working-dir` behavior.

## Worker Features

- Atomically locks the next pending issue via the `get_and_lock_next_issue` RPC function, which uses `FOR UPDATE SKIP LOCKED` to prevent race conditions when multiple workers poll simultaneously.
- Spawns `uv run rouge-adw <issue-id> --adw-id <workflow-id>` with clear logging
  so you can tail progress or read log files directly.
- Supports multiple concurrent instances with unique `--worker-id` values.
- Logs to `.rouge/logs/agents/{workflow_id}/adw_plan_build/execution.log` for
  tracking workflow progress.

## Database Requirements

All executables expect the standard Supabase schema. The worker requires the
`get_and_lock_next_issue` RPC function for atomic issue locking (see migration
`008_restore_lock_rpc`):

```sql
get_and_lock_next_issue(p_worker_id worker_id)
  RETURNS TABLE(issue_id INT, issue_description TEXT, issue_status TEXT, issue_type TEXT)
```

Uses `FOR UPDATE SKIP LOCKED` to prevent race conditions when multiple workers
poll simultaneously. Only returns issues assigned to the specified worker.

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

For the broader methodology, specs, and AI-agent prompts, see the workspace
README (`../README.md`).
