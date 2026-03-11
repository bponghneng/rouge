# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.
## Purpose

This is an agent-execution guide, not a full project manual.
Keep this file concise, actionable, and focused on how agents should work in this repo.
For user-facing setup, command reference, and operational detail, see `README.md`.

## Agent Workflow & Collaboration Rules

### Core Workflow

1. **Analyze first**: Read errors and code paths carefully before proposing changes.
2. **Research second**: Use repository search and docs; avoid assumptions.
3. **Propose clearly**: Share findings and trade-offs before non-trivial changes.
4. **Implement minimally**: Make the smallest safe change that solves the problem.
5. **Validate**: Run targeted checks/tests for touched areas and report results.
6. **Clean up**: Remove temporary debugging artifacts/files.

### Change Discipline

- **Research First**: Gather facts from code and docs before suggesting solutions.
- **Discuss Before Implementing**: For non-trivial work, get approval on approach first.
- **Respect Existing Intent**: Understand why code exists before refactoring.
- **Question Assumptions**: Investigate root causes (version drift, env differences, missing context).

### Communication

- Ask clarifying questions when requirements are ambiguous.
- Explain why a recommendation is being made, not only what to change.
- If blocked or uncertain, surface constraints and request guidance.

## Simplicity-First Principles

1. **Start with MVP**: Prioritize direct functional value.
2. **Avoid Premature Optimization**: Do not add complexity without demonstrated need.
3. **Minimize Dependencies**: Prefer existing primitives and shared utilities.
4. **Choose Clarity Over Cleverness**: Optimize for maintainability.

## Repository Map (Current)

- `src/rouge/cli/` - Main Typer CLI (`rouge`) and command groups
- `src/rouge/adw/` - ADW CLI (`rouge-adw`) orchestration entrypoint
- `src/rouge/worker/` - Worker daemon (`rouge-worker`) and artifact/state handling
- `src/rouge/core/` - Shared models, database access, workflow orchestration, agent integrations
- `src/rouge/core/workflow/` - Pipeline composition, step implementations, workflow registry
- `tests/` - Unit tests across CLI, worker, core, and workflow modules

## Workflow Routing Notes

- Workflow type resolution is centralized in `src/rouge/core/workflow/workflow_registry.py`.
- Use `get_pipeline_for_type(workflow_type)` as the public entrypoint for pipeline resolution.

## Execution Guardrails

- Use `uv`-based commands from `README.md` for setup and execution.
- After code changes, run targeted checks for modified areas; at minimum consider:
  - `uv run ruff check src/`
  - `uv run mypy`
  - `uv run pytest tests/ -v`
- Prefer targeted tests first, then broader suite runs as needed.

## Source of Truth

- **Coding rules and test conventions**: `CODING_STANDARDS.md`
- **Commands, environment variables, runtime behavior**: `README.md`
- **Artifact policy details**: `src/rouge/core/workflow/ARTIFACT_POLICY.md`
