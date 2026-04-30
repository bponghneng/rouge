# Coding Standards

## Code Style Rules

- **Unused Arguments**: Prefix unused arguments in functions and methods with an underscore (`_`).
  - Example: `def handler(event, _context):` instead of `def handler(event, context):`.
  - This rule is enforced by the linter (ruff) via the `ARG` check.
- **Type Annotations in Tests**: Every test function and pytest fixture must have an explicit return type annotation. Use `-> None` for test functions and void fixtures; use the concrete return type (e.g., `WorkflowContext`, `Issue`) for fixtures that return a value. No exceptions — mypy and reviewers will flag missing annotations.
- **CLI Option Hygiene**: For new/updated Typer options, keep `show_default=True` where appropriate and normalize/validate string inputs (reject whitespace-only values, pass trimmed values downstream). Never expose internal sentinel values (e.g., `__UNSET_SENTINEL_VALUE__`) in `--help` output; use a descriptive placeholder instead.
- **Input Validation**: String fields that originate from user input (CLI args, API payloads, model constructors) must be `.strip()`-ped and rejected if empty after stripping before reaching persistence or downstream logic. Positive integer fields (e.g., `issue_id`, `comment_id`) must be validated `> 0` at the earliest entry point, not silently passed to the database.
- **Exception Handling — Narrow Exception Types**: Never use a bare `except` or `except Exception` to swallow errors silently. Catch only the specific exceptions you expect (e.g., `subprocess.TimeoutExpired`, `FileNotFoundError`, `StepInputError`). If a broad catch is unavoidable at a boundary, always re-raise or log at ERROR level with the original traceback. Broad catches mask real bugs and make debugging significantly harder.
- **Capture Repeated Pure-Function Calls**: A function or method that returns a stable value (e.g., a config getter like `get_max_acceptance_iterations()`) must not be called inside a loop on every iteration. Capture the result to a local variable before the loop.
- **No Duplicate Utility Functions**: A utility function used by two or more modules must live in a single shared location (e.g., `rouge.core.utils`) and be imported from there. Duplicate definitions are not permitted regardless of how small the function is.
- **Workflow Dependency Declarations**: Keep step registry comments and `dependencies=[...]` declarations aligned so dependency requirements are explicit and accurate.
- **Test Isolation**: When a test path can emit comments or trigger external integrations, patch those external helpers in the step module to avoid network/database side effects.

## Workflow Step Conventions

- **File naming**: Step class files use snake_case with a `_step` suffix. Class name maps directly to filename: `FetchIssueStep` → `fetch_issue_step.py`, `FullPlanStep` → `full_plan_step.py`.
- **Step registry**: Every step must declare its `dependencies=[...]` explicitly and keep those declarations in sync with the step registry comments.
