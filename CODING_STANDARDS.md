# Coding Standards

## Code Style Rules

- **Unused Arguments**: Prefix unused arguments in functions and methods with an underscore (`_`).
  - Example: `def handler(event, _context):` instead of `def handler(event, context):`.
  - This rule is enforced by the linter (ruff) via the `ARG` check.
- **Type Annotations in Tests**: Add explicit return annotations for test functions and fixtures (`-> None` for tests, concrete types for fixtures like `WorkflowContext`/`Issue`).
- **CLI Option Hygiene**: For new/updated Typer options, keep `show_default=True` where appropriate and normalize/validate string inputs (reject whitespace-only values, pass trimmed values downstream).
- **Workflow Dependency Declarations**: Keep step registry comments and `dependencies=[...]` declarations aligned so dependency requirements are explicit and accurate.
- **Test Isolation**: When a test path can emit comments or trigger external integrations, patch those external helpers in the step module to avoid network/database side effects.
