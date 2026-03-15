---
description: ADW step: researches a task, explores affected codebase areas, and produces a simplicity-first implementation plan as JSON. Accepts the task description as $ARGUMENTS.
model: opus
thinking: true
disable-model-invocation: true
---

# Triage a Task into an Implementation Plan

Create a new implementation plan for the task described below.

## Instructions

- IMPORTANT: The `Task` describes the work that must be done. You are not implementing it; you are creating an implementation plan.
- Apply a **simplicity-first** mindset:
  - **Start with MVP**: Focus on core functionality that delivers immediate value
  - **Avoid Premature Optimization**: Don't add features "just in case"
  - **Minimal Dependencies**: Only add what's absolutely necessary for requirements
  - **Clear Over Clever**: Simple, maintainable solutions over complex architectures
- Research the codebase to understand the problem, the affected areas, and a solid solution that fits existing patterns.
- Do not save the plan to the filesystem. The plan lives only in the response.
- Produce the plan and include it verbatim in the JSON `plan` field.

## Output Format

CRITICAL: You MUST deliver your final response using the StructuredOutput tool. Do NOT return plain text. If you use subagents or research tasks, you MUST still call StructuredOutput as your very last action with the complete JSON object below.

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "task": "<brief task name>",
  "output": "plan",
  "plan": "<complete research-based plan>",
  "summary": "<concise summary of the work done>"
}

## Task

$ARGUMENTS
