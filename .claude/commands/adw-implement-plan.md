---
description: Execute a plan
thinking: true
---

# Implement Plan (Orchestrator)

You are an **orchestrator**. Delegate each implementation step to a subagent. Do NOT implement code directly.

## Instructions

### 1. Parse the Plan

- Read `CLAUDE.md` for project conventions
- Locate the **Implementation Plan** section in `$ARGUMENTS`
- Extract each numbered step (plans may have flat steps or phases with sub-steps)
- Note any **Task Context** constraints — these apply to all steps

### 2. Delegate Each Step

For each step, spawn a subagent using the Task tool:

```
Task(
  subagent_type: "general-purpose",
  description: "<step number>: <brief title>",
  prompt: <see guidance below>
)
```

**Subagent prompt guidance** (keep it minimal):
- Include the step text verbatim from the plan
- Include relevant constraints from Task Context (if any)
- Mention files referenced in that step
- Note what prior steps accomplished (if this step depends on them)
- Ask subagent to read CLAUDE.md, research, implement, and report files modified

Trust subagents to figure out implementation details. Do not over-specify.

### 3. Execute Sequentially

- Run steps in order, waiting for each to complete
- Track what each step produced for dependent steps
- Stop on failure

### 4. Aggregate Results

After all steps complete:
- Run `git diff --stat`
- Compile the list of all modified files
- Summarize work done

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "files_modified": ["path/to/file1.ext"],
  "git_diff_stat": "<git diff --stat output>",
  "output": "implement-plan",
  "status": "completed",
  "summary": "<summary>"
}


## Plan Content

$ARGUMENTS
