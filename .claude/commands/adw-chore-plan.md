---
description: Triage a chore and produce a size-aware, simplicity-first implementation plan.
---

# Triage a Chore for Immediate Implementation

Create a new implementation plan for a codebase chore using the `Plan Format` below. The goal is to give an implementer just enough clarity to execute confidently, while keeping the plan as small and simple as the chore allows.

## Instructions

- IMPORTANT: The `Chore` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- First, decide whether this is a **small-change**, **medium-change**, or **large-refactor** chore and record that in the plan. Use that scope to right-size your research effort and the amount of detail.
- Apply a **simplicity-first** mindset (see `rouge/CLAUDE.md`): prefer the smallest coherent change that solves the problem, avoid premature abstractions, and keep dependencies minimal.
- Research the codebase just enough to understand the problem and a solid solution. For small changes, rely mainly on direct code inspection and existing docs; for larger refactors, plan for a deeper pass.
- Use the `Research Method` section as guidance, not a checklist; you may skip steps that are clearly unnecessary for small chores.
- You may use subagents (`research-specialist`, `python-architect`, `taskmaster`) when helpful:
  - `research-specialist` for external docs and best practices.
  - `python-architect` for architecture / design questions.
  - `taskmaster` to refine the implementation steps into increments of 1–2 days for a single engineer.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan in the exact `Plan Format` and include it verbatim in the JSON `plan` field.
- Replace every `<placeholder>` in the `Plan Format` with the requested value before outputting JSON.
- Follow the `Plan Guidelines` when drafting the plan.

## Research Method

- Start by reading `CLAUDE.md`, `README.md`, and any project-level instructions referenced there.
- Clearly state the specific problem or opportunity the chore addresses and what is explicitly out of scope.
- Identify the smallest set of files and modules that are relevant to the chore. Understand how they currently work and why they matter.
- Consider whether any legacy patterns need to be respected, adapted, or refactored for this chore.
- For small chores, keep research light and focused. For medium/large refactors, you may:
  - Consult `research-specialist` for relevant external documentation or prior art.
  - Consult `python-architect` for architectural implications and design options.

## Plan Guidelines

- Propose test coverage only for critical paths touched by the chore. Focus on core functionality; avoid exhaustive edge-case enumeration.
- Keep your analysis and recommendations as simple and concise as possible while still enabling a high-confidence implementation.
- Follow existing patterns and conventions in the codebase. Do not invent new patterns unless necessary, and call out when you do.
- For small-change chores, keep the overall plan concise:
  - Fill in `Task Context`, `Description` and `Relevant Files`
  - Fill in a short `Implementation Plan`
  - Fill in a minimal `Validation`
  - Use `Notes / Future Considerations` only when it clearly adds value.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "type": "chore",
  "output": "plan",
  "plan": <full plan in the exact `Plan Format`>,
  "summary": <concise summary of the work done>
}

### Plan Format

```md
# Chore Plan: <chore name>

## Task Context (Required)

- Scope: <small-change | medium-change | large-refactor>
- Goal: <1–2 bullets describing the outcome of this chore>
- Constraints: <any key assumptions, constraints, or dependencies (optional)>

## Description (Required)

<2–4 bullets describing the problem this chore solves, the desired outcome, and any important out-of-scope items.>

## Relevant Files (Required)

<list only the files that are relevant to implementing this chore and briefly describe why each is relevant.>

#### New Files (Optional)

<list any new files that are expected to be created for this chore, with a short note on their purpose.>

## Implementation Plan (Required)

<describe how to implement this chore in a way that matches the scope:>

- For **small changes**, provide a single ordered list of 3–7 concrete steps.
- For **medium/large refactors**, group steps into phases (e.g., "Phase 1", "Phase 2") with ordered lists under each.
- Each step should be a unit of work that can be completed in 1–2 days by a single engineer.
- Include where tests or validation are added or updated, but avoid over-specifying trivial details that can be left to the implementer’s judgement.

## Validation (Required)

Explain how to validate that the chore is complete and has no obvious regressions.

<list the commands to run (e.g., linting, targeted tests, or other existing project commands) and briefly state what each command is validating. Choose a level of validation that gives high confidence appropriate to the scope and risk of the chore. Avoid using raw curl commands for validation.>

Run these commands from `rouge/` to validate changes:

- `uv run mypy` - Static type checking
- `uv run pytest tests/ -v` - Run unit tests with verbose output
- `uv run ruff check src/` - Fast Python linter
- `uv run black src/` - Code formatter

## Notes / Future Considerations (Optional)

<optionally list any additional notes, follow-up ideas, or context that might inform future improvements or related chores.>
```


## Chore

$ARGUMENTS
