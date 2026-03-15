---
description: Triage a task and produce a size-aware, simplicity-first implementation plan.
---

# Triage a Task into an Implementation Plan

Create a new implementation plan for the task described below. The goal is to give an implementer just enough clarity to build confidently, while keeping the plan as small and simple as the task allows.

## Instructions

- IMPORTANT: The `Task` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- First, decide whether this is a **small-change**, **medium-change**, or **large-refactor** task and record that in the plan.
- Apply a **simplicity-first** mindset (see `rouge/CLAUDE.md`): prefer the smallest coherent implementation that delivers the desired value, avoid premature abstractions, and keep dependencies minimal.
- Research the codebase just enough to understand the problem, the affected areas, and a solid solution that fits existing patterns.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan in the exact `Plan Format` and include it verbatim in the JSON `plan` field.
- Replace every `<placeholder>` in the `Plan Format` with the requested value before outputting JSON.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "task": "<brief task name>",
  "output": "plan",
  "plan": "<full plan in the exact `Plan Format`>",
  "summary": "<concise summary of the work done>"
}

### Plan Format

```md
# Task Plan: <task name>

## Task Context (Required)

- Scope: <small-change | medium-change | large-refactor>
- Goal: <1–2 bullets describing the outcome of this task>
- Constraints: <any key assumptions, constraints, or dependencies (optional)>

## Description (Required)

<2–4 bullets describing the task, its purpose, and the value it delivers.>

## Relevant Files (Required)

<list only the files that are relevant to implementing this task and briefly describe why each is relevant.>

#### New Files (Optional)

<list any new files expected to be created for this task, with a short note on their purpose.>

## Implementation Plan (Required)

<describe how to implement this task in a way that matches the scope:>

- For **small changes**, provide a single ordered list of 3–7 concrete steps.
- For **medium/large tasks**, group steps into phases with ordered lists under each.
- Each step should be a unit of work that can be completed in 1–2 days by a single engineer.

## Validation (Required)

Run these commands from `rouge/` to validate changes:

- `uv run mypy` - Static type checking
- `uv run pytest tests/ -v` - Run unit tests with verbose output
- `uv run ruff check src/` - Fast Python linter
- `uv run black src/` - Code formatter

## Notes / Future Considerations (Optional)

<optionally list any additional notes or follow-up ideas.>
```

## Task

$ARGUMENTS
