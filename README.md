# Rouge

Rouge is a Python workflow runner for software-development issues stored in
Supabase. It gives you:

- `rouge`: the main CLI for issue management, workflow execution, and comments
- `rouge-adw`: a single-issue workflow runner
- `rouge-worker`: a queue worker that continuously polls for assigned work

Rouge's supported coding agent is **Claude Code**. Workflow planning,
implementation, and code-quality/PR composition all run through Claude Code.

## What Rouge does

Rouge executes issue-driven workflows against one or more local repositories.
The built-in workflow types are:

- `full`: fetch issue, prepare a branch, build a plan, implement it, run code
  quality, compose a PR/MR, and optionally create one
- `thin`: a lighter workflow for straightforward work; skips code-quality and
  creates a draft PR/MR when publishing is enabled
- `patch`: check out an existing branch, build a patch plan, implement it, run
  code quality, and push commits to an existing PR/MR
- `direct`: fetch issue, prepare a branch/worktree, and implement directly
  from the issue description without a planning step

Workflow state is persisted as typed artifacts under
`<WORKING_DIR>/.rouge/workflows/<workflow-id>/`.

## Install

```bash
cd rouge
uv sync
uv run rouge --help
```

## Required environment

Rouge loads a `.env` file from the current directory when available, otherwise
from the parent directory, or directly from the shell environment.

Required to talk to Supabase:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Required to execute Claude-driven workflow steps:

- `ANTHROPIC_API_KEY`

Required for workflows that create/reset local branches:

- `ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true`

That flag is intentionally explicit because the git setup step uses destructive
operations such as `git reset --hard` and branch deletion. Run Rouge in a clean,
disposable, or dedicated working tree.

## Common optional environment

- `WORKING_DIR`: base directory for runtime state; defaults to the current
  directory
- `REPO_PATH`: comma-separated repo roots; defaults to the current directory
- `DEFAULT_GIT_BRANCH`: default branch used by git setup; defaults to `main`
- `CLAUDE_CODE_PATH`: Claude Code CLI path; defaults to `claude`
- `ROUGE_PROMPT_TIMEOUT`: timeout in seconds for a single Claude Code call;
  defaults to `1800`
- `ROUGE_WORKFLOW_TIMEOUT_SECONDS`: timeout in seconds for a workflow run;
  defaults to `3600`
- `DEV_SEC_OPS_PLATFORM`: set to `github` or `gitlab` to enable PR/MR creation
- `GITHUB_PAT`: required for automatic GitHub PR creation; requires `gh`
- `GITLAB_PAT`: required for automatic GitLab MR creation or patch updates;
  requires `glab`

## Quick start

```bash
# Create a full issue
uv run rouge issue create "Fix the authentication bug in the login flow"

# Run a full workflow
uv run rouge workflow run 123

# Run a thin workflow
uv run rouge workflow thin 123

# Run a patch workflow
uv run rouge workflow patch 123

# Run a direct workflow
uv run rouge workflow direct 123

# Run the single-issue ADW entrypoint directly
uv run rouge-adw 123 --workflow-type full

# Start a worker
uv run rouge-worker --worker-id alleycat-1
```

## CLI surface

Main command groups:

- `rouge issue`: `create`, `read`, `list`, `update`, `delete`, `reset`
- `rouge workflow`: `run`, `patch`, `thin`, `direct`
- `rouge comment`: `list`, `read`
Use `uv run rouge <group> --help` for full arguments and options.

## Issues and workflows

Issue types:

- `full`
- `patch`
- `thin`
- `direct`

Examples:

```bash
# Description only; title is auto-generated
uv run rouge issue create "Fix the login button styling on mobile"

# Explicit title
uv run rouge issue create "Fix the login button styling on mobile" \
  --title "Mobile login button fix"

# From a spec file
uv run rouge issue create --spec-file spec.md --title "Implement feature X"

# Patch issue targeting an existing branch
uv run rouge issue create "Apply follow-up fixes" \
  --type patch \
  --branch feature/my-branch
```

Patch issues can also inherit a branch from a parent issue via
`--parent-issue-id`.

## Worker operation

`rouge-worker` polls Supabase for assigned pending issues, locks work
atomically, and shells out to `rouge-adw`.

Common options:

- `--worker-id`: required unique identifier
- `--poll-interval`: seconds between polls; defaults to `10`
- `--log-level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `--workflow-timeout`: workflow timeout override in seconds

The worker also supports:

```bash
uv run rouge-worker reset alleycat-1
```

to reset a failed worker artifact back to `ready`.

## Runtime layout

Rouge stores runtime state under `<WORKING_DIR>/.rouge/`, including:

- `workflows/<workflow-id>/`: workflow artifacts
- `workers/<worker-id>/`: worker state artifacts
- `agents/logs/<workflow-id>/`: saved prompts and agent logs

## Development

```bash
uv run ruff check src/
uv run mypy
uv run pytest tests/ -v
```

## Repository layout

```text
src/rouge/cli/      Main Typer CLI
src/rouge/adw/      Single-issue workflow runner
src/rouge/worker/   Queue worker and worker state handling
src/rouge/core/     Shared models, database access, agents, and workflow logic
tests/              Unit tests
```

