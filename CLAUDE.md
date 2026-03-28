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

## Coding Standards

Follow `CODING_STANDARDS.md` for repository-wide code style and testing standards.

## Development Commands

**Package Management**: uv (fast Python package manager). Run `uv sync` to install dependencies.

**CLI Entry Points**:
- `uv run rouge` - Main CLI (issue, workflow, step, artifact subcommands)
- `uv run rouge-adw <issue-id>` - Execute ADW workflow for a single issue
- `uv run rouge-worker --worker-id <id>` - Start background worker daemon

**Code Quality**:
- `uv run ruff check src/` — lint
- `uv run black src/` — format
- `uv run mypy` — type check

**Testing**:
- `uv run pytest tests/ -v` — run tests
- `uv run pytest --cov=src/rouge` — run with coverage

See `README.md` for the full command reference (issue, workflow, step, artifact subcommands).

## Architecture

- `src/rouge/cli/` - Typer CLI entry point with issue/workflow/step/artifact subcommands
- `src/rouge/adw/` - Agent Development Workflow CLI for single issue execution
- `src/rouge/worker/` - Background daemon for polling and processing issues from Supabase
- `src/rouge/core/` - Shared foundation: Supabase client, models, utilities, workflow orchestration
- `src/rouge/core/workflow/` - Workflow pipeline with steps (fetch, plan, implement, code-quality, compose-request)
- `src/rouge/core/workflow/artifacts.py` - Typed artifacts and filesystem-backed store under `<WORKING_DIR>/.rouge/workflows/<workflow-id>/`
- `src/rouge/core/workflow/step_registry.py` - Step registry with artifact dependencies/outputs
- `src/rouge/core/agents/` - AI agent integrations (Claude, OpenCode)
- `tests/` - Unit tests for all modules

**Workflow Registry**: `workflow_registry.py` provides a declarative registration system. All workflow type resolution goes through the `WorkflowRegistry` singleton. Entry point: `get_pipeline_for_type(workflow_type)`.

## Testing Strategy

Tests are in `tests/` and use pytest with async support via `pytest-asyncio`. Mock all external dependencies (Supabase, AI agents) for isolation.
