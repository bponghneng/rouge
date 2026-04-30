---
description: ADW step: researches a complex feature-level task, explores affected codebase areas, and produces a structured implementation plan as JSON. Accepts the task description as $ARGUMENTS.
model: opus
thinking: true
disable-model-invocation: true
---

# Triage a Complex Task into an Implementation Plan

Create a research-backed implementation plan for the task described below. This prompt is for feature-level or higher-complexity work where the implementer needs context, sequencing, validation strategy, and risk awareness before making changes.

## Instructions

- IMPORTANT: The `Task` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- Apply a **simplicity-first** mindset:
  - **Start with MVP**: Focus on core functionality that delivers immediate value
  - **Avoid Premature Optimization**: Don't add features "just in case"
  - **Minimal Dependencies**: Only add what's absolutely necessary for requirements
  - **Clear Over Clever**: Simple, maintainable solutions over complex architectures
- Research the codebase to understand the problem, existing patterns, affected components, constraints, and a solid solution path.
- Include enough context for another engineer or agent to implement safely without re-discovering the high-level design.
- Call out explicit non-goals and scope boundaries so the plan does not expand into broad rewrites unless the task requires them.
- Make validation proportional to scope and risk. Prefer targeted checks first, but call for broader tests, static analysis, or integration checks when the change touches shared workflow, command-line, persistence, artifact, or multi-call-site behavior.
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
  "summary": "<concise summary of the planned work>"
}

### Plan Format

```md
# Implementation Plan: <task name>

## Problem Statement

<briefly describe what needs to change and why it matters.>

## Current State

<summarize the relevant current implementation, files/modules/workflows/data flows, and constraints discovered during research.>

## Proposed Approach

<describe the high-level design, key decisions, why they fit existing patterns, and any explicit non-goals.>

## Implementation Phases

### Phase 1: <foundation or preparation>

<ordered list of concrete steps.>

### Phase 2: <core behavior>

<ordered list of concrete steps.>

### Phase 3: <integration, cleanup, or follow-through>

<ordered list of concrete steps. Omit this phase if not needed, but keep phases meaningful for the task scope.>

## Validation

- Targeted tests: <specific test files, cases, or coverage to add/update for the changed behavior>
- Integration checks: <workflow, command-line, persistence, artifact, or cross-component paths to exercise when relevant>
- Static analysis: <project-standard linting, formatting, type checking, or equivalent static checks to run when code changes warrant them>
- Broader suite: <state whether the project-standard broader test suite is warranted because the work touches shared behavior; if not, explain why targeted tests are sufficient>

## Risks and Follow-ups

<known risks, assumptions, open questions, and deferred follow-up work. Use "None identified" if there are no meaningful items.>
```

## Task

$ARGUMENTS
