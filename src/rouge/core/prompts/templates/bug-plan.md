---
description: Triage a bug and produce a size-aware, simplicity-first implementation plan.
---

# Triage a Bug for Immediate Implementation

Create a new implementation plan for a bug using the `Plan Format` below. The goal is to give an implementer just enough clarity to fix the bug confidently and surgically, while keeping the plan as small and simple as the bug allows.

## Instructions

- IMPORTANT: The `Bug` describes the behavior that must be corrected. You are not fixing it; you are creating an implementation plan.
- First, decide whether this is a **small-change**, **medium-change**, or **large-refactor** bug and record that in the plan. Use that scope to right-size your research effort and the amount of detail.
- Apply a **simplicity-first** mindset (see `rouge/CLAUDE.md`): prefer the smallest coherent change that fixes the bug, avoid unrelated refactors and premature abstractions, and keep dependencies minimal.
- Research the codebase just enough to reliably reproduce the bug (or explain why it cannot be reproduced), understand the likely root cause, and outline a safe fix.
- Use the `Research Method` section as guidance, not a checklist; you may skip steps that are clearly unnecessary for small bugs.
- You may use subagents (`research-specialist`, `python-architect`, `taskmaster`) when helpful:
  - `research-specialist` for external docs and best practices.
  - `python-architect` for architecture / design questions.
  - `taskmaster` to refine the implementation steps into increments of 1–2 days for a single engineer.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan in the exact `Plan Format` and include it verbatim in the JSON `plan` field.
- Replace every `<placeholder>` in the `Plan Format` with the requested value before outputting JSON.
- Follow the `Plan Guidelines` when drafting the plan.

## Research Method

- Start by reading `CLAUDE.md` and `README.md`, and any project-level instructions referenced there.
- Clearly state where and how the bug manifests (feature area, environment, conditions) and what is explicitly out of scope.
- Reproduce the bug if possible and document the most reliable reproduction steps. If reproduction is not possible, describe why and what evidence you are relying on.
- Identify the smallest set of files and modules that are relevant to the bug. Understand how they currently behave and why they are likely involved in the root cause.
- Consider whether any legacy patterns or workarounds contribute to the bug and how they should be handled (respected, adapted, or refactored).
- For small bugs, keep research light and focused. For medium/large bugs, you may:
  - Consult `research-specialist` for relevant external documentation or prior art.
  - Consult `python-architect` for architectural implications and design options.

## Plan Guidelines

- Propose test coverage only for critical paths touched by the bug fix. Focus on core behavior; avoid exhaustive edge-case enumeration.
- Keep your analysis and recommendations as simple and concise as possible while still enabling a high-confidence fix.
- Follow existing patterns and conventions in the codebase. Do not invent new patterns unless necessary, and call out when you do.
- For small-change bugs, keep the overall plan concise:
  - Fill in  `Task Context`, `Bug Description`, `Steps to Reproduce`, `Root Cause Hypothesis` and `Relevant Files`
  - Fill in a short `Implementation Plan`
  - Fill in a minimal `Validation`
  - Use `Notes / Future Considerations` only when it clearly adds value.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "type": "bugfix",
  "output": "plan",
  "plan": <full plan in the exact `Plan Format`>,
  "summary": <concise summary of the work done>
}

### Plan Format

```md
# Bug Plan: <bug name>

## Task Context (Required)

- Scope: <small-change | medium-change | large-refactor>
- Area: <api | app-ionic | app-old | shared | other>
- Environment(s): <dev | staging | prod | test> (where the bug is observed)
- Goal: <1–2 bullets describing what "fixed" means for this bug>

## Bug Description (Required)

<2–4 bullets describing the visible symptoms, expected vs actual behavior, and any relevant context (e.g., feature, user type, device).>

## Steps to Reproduce (Required)

<ordered list of steps to reproduce the bug. If the bug cannot be reproduced reliably, describe the best-known scenario and any uncertainty.>

## Root Cause Hypothesis (Required)

<brief analysis of the likely root cause(s). Reference specific modules, functions, components, or queries when possible. Note any uncertainties that need to be resolved during implementation.>

## Relevant Files (Required)

<list only the files that are relevant to understanding and fixing this bug and briefly describe why each is relevant.>

#### New Files (Optional)

<list any new files expected to be created for the fix, with a short note on their purpose.>

## Implementation Plan (Required)

<describe how to fix this bug in a way that matches the scope:>

- For **small changes**, provide a single ordered list of 3–7 concrete steps.
- For **medium/large bugs**, group steps into phases (e.g., "Phase 1", "Phase 2") with ordered lists under each.
- Each step should be a unit of work that can be completed in 1–2 days by a single engineer.
- Emphasize minimal, targeted changes that address the root cause while avoiding unrelated refactors.
- Include where tests or validation are added or updated, but avoid over-specifying trivial details that can be left to the implementer’s judgement.

## Validation (Required)

Explain how to validate that the bug is fixed and that there are no obvious regressions.

<list the commands to run (e.g., linting, targeted tests, or other existing project commands) and briefly state what each command is validating. Include any manual verification steps if they are important. Choose a level of validation that gives high confidence appropriate to the scope and risk of the bug. Avoid using raw curl commands for validation.>

## Notes / Future Considerations (Optional)

<optionally list any additional notes, follow-up ideas, or context that might inform future improvements or related bug fixes.>
```


## Bug

$ARGUMENTS
