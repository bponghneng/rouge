---
description: ADW step: produces a concise, direct implementation plan for small low-complexity tasks as JSON with minimal inspection. Accepts the task description as $ARGUMENTS.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Produce a Concise Implementation Plan

Create a minimal implementation plan for the small task described below.

## Instructions

- IMPORTANT: The `Task` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- This is a simple, direct task. Produce a concise plan with clear steps. Do only enough inspection to identify the narrow implementation path.
- Apply a **simplicity-first** mindset: prefer the smallest coherent change that satisfies the task and avoid unrelated refactors.
- Do not include phases, architecture discussion, broad exploration, or speculative cleanup.
- Make validation minimal and targeted. Every plan must include validation, but docs-only or prompt-only changes may use manual verification instead of automated tests.
- Do not call for the full test suite unless the task touches shared behavior, public interfaces, workflow orchestration, or multiple call sites.
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
  "summary": "<concise summary of the planned work>"
}

### Plan Format

```md
# Thin Plan: <task name>

## Goal

<one concise outcome, or 1–2 bullets if needed>

## Touch Points

<list the likely file(s), module(s), or narrow search needed. If exact files are unknown, describe the smallest search required to find them.>

## Steps

<provide a single ordered list of 2–5 concrete implementation steps. Each step should be directly actionable with no ambiguity. Do not use phases.>

## Validation

<run the smallest targeted check that matches the change:>

- Code behavior: run the project-standard targeted test for the changed behavior
- Command-line behavior: run the relevant project-standard command or targeted command-line test
- Docs/prompt-only change: no automated tests required; manually verify the updated text matches the current implementation
- Shared behavior: add project-standard static analysis and broader tests only if the small change affects shared code or multiple call sites
```

## Task

$ARGUMENTS
