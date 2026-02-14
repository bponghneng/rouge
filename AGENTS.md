# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

Rouge is a workflow automation stack that orchestrates AI coding agents for software development tasks. It provides Typer CLIs and an automated worker daemon built on a shared core foundation with Supabase integration for issue tracking and workflow orchestration.

## Workflow Style & Collaboration Rules

### Code Changes & Investigation Workflow

- **Research First**: Investigate thoroughly before proposing solutions. Use search
  tools and documentation to gather facts rather than making assumptions.
- **Discuss Before Implementing**: Present findings and proposed approaches for
  approval before making code changes. Explain options and trade-offs.
- **Respect Original Code**: Try to understand where code came from and what problem
  it's solving before assuming it can be changed.
- **Question Assumptions**: If something doesn't work as expected, investigate the
  root cause. Look for version differences, environment issues, or missing context.

### Problem-Solving Workflow

1. **Analyze**: Read errors carefully and identify the real issue
2. **Research**: Use tools and documentation to understand the problem context
3. **Propose**: Present findings and suggest solution options with pros/cons
4. **Implement**: Only after approval, make minimal necessary changes
5. **Clean Up**: Remove temporary test files or debugging code

### Communication

- Ask clarifying questions when requirements are unclear
- Explain the "why" behind recommendations
- If blocked or uncertain, ask for guidance rather than guessing

## Simplicity-First Mindset

Your guidance is directed by these core principles:

1. **Start with MVP**: Focus on core functionality that delivers immediate value
2. **Avoid Premature Optimization**: Don't add features "just in case"
3. **Minimal Dependencies**: Only add what's absolutely necessary for requirements
4. **Clear Over Clever**: Simple, maintainable solutions over complex architectures

Apply these principles when evaluating whether complex patterns, or advanced optimizations are truly needed or if simpler solutions would suffice.

## Code Style Rules

- **Unused Arguments**: Prefix unused arguments in functions and methods with an underscore (`_`).
  - Example: `def handler(event, _context):` instead of `def handler(event, context):`.
  - This rule is enforced by the linter (ruff) via the `ARG` check.

## Development Commands

**Package Management**: uv (fast Python package manager)

**CLI Entry Points**:
- `uv run rouge` - Launch the main CLI (shows help or runs subcommands)
- `uv run rouge-adw <issue-id>` - Execute ADW workflow for a single issue
- `uv run rouge-worker --worker-id <id>` - Start background worker daemon

**Code Quality Tools**:

- `ruff`: `uv run ruff check src/` - Fast Python linter
- `black`: `uv run black src/` - Code formatter
- `mypy`: `uv run mypy` - Static type checking

**Testing**:
- `pytest`: `uv run pytest tests/ -v` - Run unit tests with verbose output
- `pytest-cov`: `uv run pytest --cov=rouge` - Run tests with coverage

**Workflow Commands**:
- `uv run rouge run <issue-id>` - Execute workflow synchronously
- `uv run rouge create "description"` - Create a new issue
- `uv run rouge create-from-file <file>` - Create issue from file
- `uv run rouge step list|run|deps|validate` - Inspect and run individual steps
- `uv run rouge artifact list|show|delete|types|path` - Inspect and manage workflow artifacts

**Setup**: `uv sync` - Install dependencies and sync virtual environment

## Architecture

**Current Structure**:

- `src/rouge/cli/` - Typer CLI entry point with subcommands (create, run)
- `src/rouge/adw/` - Agent Development Workflow CLI for single issue execution
- `src/rouge/worker/` - Background daemon for polling and processing issues from Supabase
- `src/rouge/core/` - Shared foundation: Supabase client, models, utilities, workflow orchestration
- `src/rouge/core/workflow/` - Workflow pipeline with steps (fetch, classify, plan, implement, review)
- `src/rouge/core/workflow/artifacts.py` - Typed artifacts and filesystem-backed store under `<WORKING_DIR>/.rouge/workflows/<workflow-id>/`
- `src/rouge/core/workflow/step_registry.py` - Step registry with artifact dependencies/outputs
- `src/rouge/core/agents/` - AI agent integrations (Claude, OpenCode)
- `src/rouge/tui/` - Textual-based terminal user interface components
- `tests/` - Unit tests for all modules

**Workflow Registry**:

The `workflow_registry.py` module provides a declarative workflow type registration
system for centralizing workflow routing. All workflow type resolution goes through
the `WorkflowRegistry` singleton, which supports registering additional workflow
types without modifying routing code.

Entry point: `get_pipeline_for_type(workflow_type)` is the unified public API for
resolving a workflow type to its pipeline.

**Key Dependencies**:

- `typer` - CLI framework for command-line interfaces
- `textual` - TUI framework for terminal user interfaces
- `supabase` - Backend integration for issue tracking and workflow orchestration
- `pydantic` - Data validation and settings management
- `httpx` - Async HTTP client for API communication
- `python-dotenv` - Environment variable loading from .env files

## Workflow Steps Naming Convention

All workflow step files follow a consistent `_step` suffix pattern:

- **File naming**: Step class files use snake_case with a `_step` suffix
- **Class-to-file mapping**: Class name converted to snake_case with `_step` appended
  - Example: `GitSetupStep` → `git_setup_step.py`
  - Example: `FetchIssueStep` → `fetch_issue_step.py`
  - Example: `ClassifyIssueStep` → `classify_issue_step.py`

**Exception**: `review.py` exists as a backwards-compatibility shim and does not follow this pattern.

This convention makes it easy to locate step implementations by class name and maintains consistency across the codebase.

## Testing Strategy

Tests are located in `tests/` and use pytest with async support.

- Unit tests cover core functionality, CLI commands, workflow steps, and agent integrations
- Use `pytest-asyncio` for testing async code
- Tests mock external dependencies (Supabase, AI agents) for isolation
- Run `uv run pytest tests/ -v` for verbose test output
