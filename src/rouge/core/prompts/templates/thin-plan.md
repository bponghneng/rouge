---
description: ADW step: produces a concise, direct implementation plan for simple tasks as JSON with no deep research or exploration. Accepts the task description as $ARGUMENTS.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Produce a Concise Implementation Plan

Create a minimal implementation plan for the task described below.

## Instructions

- IMPORTANT: The `Task` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- This is a simple, direct task. Produce a concise plan with clear steps. Skip deep research or exploration — focus on the implementation path.
- Apply a **simplicity-first** mindset: prefer the smallest coherent change that satisfies the task and avoid unrelated refactors.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan in the exact `Plan Format` and include it verbatim in the JSON `plan` field.
- Replace every `<placeholder>` in the `Plan Format` with the requested value before outputting JSON.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "type": "thin",
  "output": "plan",
  "plan": "<full plan in the exact `Plan Format`>",
  "summary": "<concise summary of the work done>"
}

### Plan Format

```md
# Thin Plan: <task name>

## Goal

<1–2 bullets describing the outcome of this task>

## Changes

<list the specific file-by-file changes required. Use direct bullets that mirror the task.>

## Steps

<provide a single ordered list of 3–7 concrete implementation steps. Each step should be directly actionable with no ambiguity.>

## Validation

Run these commands from `rouge/` to validate changes:

- `uv run mypy` - Static type checking
- `uv run pytest tests/ -v` - Run unit tests with verbose output
- `uv run ruff check src/` - Fast Python linter
- `uv run black src/` - Code formatter
```

## Task

$ARGUMENTS
