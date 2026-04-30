---
description: ADW step: scopes targeted remediation or follow-up work and produces a delta-focused implementation plan as JSON. Accepts the patch description as $ARGUMENTS.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Triage Remediation into a Patch Plan

Create a remediation-focused implementation plan for a patch using the `Plan Format` below. The goal is to give an implementer clear, direct steps to correct an existing implementation, review finding, regression, or incomplete behavior with minimal changes.

## Instructions

- IMPORTANT: The `Patch` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- Apply a **simplicity-first** mindset: prefer the smallest coherent change that satisfies the patch request and avoid unrelated refactors.
- Treat the patch as a delta from current behavior. Identify what is wrong or incomplete, what must change, and what already-working behavior must be preserved.
- Inspect the current implementation and patch context before planning. Use external documentation search only when the patch depends on external interfaces or behavior that cannot be verified from the repository.
- Keep the plan targeted. Do not include opportunistic cleanup, broad rewrites, or unrelated refactors unless they are required to fix the patch.
- Make validation regression-focused and proportional to scope and risk. Prefer targeted checks first; only call for broad test suites, full static analysis, or full integration validation when the patch affects shared behavior, public interfaces, workflow orchestration, or multiple call sites.
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
  "summary": "<concise summary of the planned work>"
}

### Plan Format

```md
# Patch Plan: <patch name>

## Remediation Target (Required)

- Scope: <small-change | medium-change | large-refactor>
- Target: <the existing behavior, implementation, review finding, regression, or incomplete work being corrected>
- Goal: <1–2 bullets describing the expected outcome of this patch>
- Preserve: <existing behavior or interfaces that must not change>
- Constraints: <key assumptions, constraints, dependencies, or "None">

## Current Problem (Required)

<describe the specific defect, gap, drift, or incomplete behavior. Name affected files/components when known.>

## Targeted Changes (Required)

<list the specific file-by-file or component-level changes required by the patch request. Use direct bullets that mirror the request and avoid unrelated cleanup.>

## Implementation Steps (Required)

<describe how to implement this patch in a direct way that matches the scope:>

- For **small changes**, provide a single ordered list of 3–7 concrete steps.
- For **medium/large refactors**, group steps into phases with ordered lists under each.
- Include a step to add or update regression coverage when behavior changes.
- Emphasize minimal, targeted changes and note what should not be disturbed.

## Regression Validation (Required)

<explain how to validate that the reported issue is fixed and that existing behavior has no obvious regressions. Include:>

- Reproduction or failure confirmation: <how to observe the original issue before/without the fix, when practical>
- Regression coverage: <test that would fail before the patch and pass after it>
- Touched-area tests: <project-standard targeted tests for the changed files, components, or behavior>
- Static analysis: <project-standard linting, formatting, type checking, or equivalent static checks when code changes warrant them>
- Broader validation: <run the project-standard broader test suite or integration checks only if the patch affects shared workflow behavior, public interfaces, or multiple call sites; otherwise state why targeted checks are sufficient>

Avoid relying on low-level ad hoc network commands for validation when safer project-standard checks are available.
```

## Patch

$ARGUMENTS
