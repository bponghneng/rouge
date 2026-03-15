---
description: Triage a patch and produce a direct, simplicity-first implementation plan.
---

# Triage a Patch into an Implementation Plan

Create a new implementation plan for a patch using the `Plan Format` below. The goal is to give an implementer clear, direct steps to apply the patch with minimal changes.

## Instructions

- IMPORTANT: The `Patch` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- Apply a **simplicity-first** mindset: prefer the smallest coherent change that satisfies the patch request and avoid unrelated refactors.
- Understand the noted issues to be addressed by examining the codebase and making use of tools for web and docs search for reference to best practices and language and framework syntax and idioms.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan in the exact `Plan Format` and include it verbatim in the JSON `plan` field.
- Replace every `<placeholder>` in the `Plan Format` with the requested value before outputting JSON.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "type": "patch",
  "output": "plan",
  "plan": "<full plan in the exact `Plan Format`>",
  "summary": "<concise summary of the work done>"
}

### Plan Format

```md
# Patch Plan: <patch name>

## Patch Summary (Required)

- Scope: <small-change | medium-change | large-refactor>
- Goal: <1–2 bullets describing the outcome of this patch>
- Constraints: <any key assumptions, constraints, or dependencies (optional)>

## Changes (Required)

<list the specific file-by-file changes required by the patch request. Use direct bullets that mirror the request.>

## Implementation Plan (Required)

<describe how to implement this patch in a direct way that matches the scope:>

- For **small changes**, provide a single ordered list of 3–7 concrete steps.
- For **medium/large refactors**, group steps into phases (e.g., "Phase 1", "Phase 2") with ordered lists under each.
- Each step should be a unit of work that can be completed in 1–2 days by a single engineer.
- Emphasize minimal, targeted changes and note where tests or validation are updated.

## Validation (Required)

Explain how to validate that the patch is complete and has no obvious regressions.

<list the commands to run (e.g., linting, formatting, type checking, targeted tests) and briefly state what each command is validating. Choose a level of validation that gives high confidence appropriate to the scope and risk of the patch. Avoid using raw curl commands for validation.>

Run these commands from `rouge/` to validate changes:

- `uv run mypy` - Static type checking
- `uv run pytest tests/ -v` - Run unit tests with verbose output
- `uv run ruff check src/` - Fast Python linter
- `uv run black src/` - Code formatter
```

## Patch

$ARGUMENTS
