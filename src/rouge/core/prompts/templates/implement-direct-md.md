---
description: ADW step: implements changes directly from an issue description by delegating each logical task to a subagent in sequence. Accepts the issue description as $ARGUMENTS and returns a JSON summary of all files modified.
model: opus
thinking: true
disable-model-invocation: true
---

# Implement Direct (Orchestrator)

You are an **orchestrator**. Break the issue specification into logical implementation tasks and delegate each to a subagent. Do NOT implement code directly.

## Instructions

### 1. Analyse the Issue Specification

- Read `CLAUDE.md` for project conventions
- Read the **Issue Specification** provided in `$ARGUMENTS`
- Decompose the specification into an ordered list of discrete implementation tasks
- Identify constraints, acceptance criteria, and dependencies between tasks

### 2. Delegate Each Task

For each task, spawn a subagent using the Task tool:

```
Task(
  subagent_type: "general-purpose",
  description: "<task number>: <brief title>",
  prompt: <see guidance below>
)
```

**Subagent prompt guidance** (keep it minimal):
- Describe the task clearly, referencing the relevant part of the issue spec
- Include any constraints or acceptance criteria that apply
- Mention files likely to be affected
- Note what prior tasks accomplished (if this task depends on them)
- Ask subagent to read CLAUDE.md, research, implement, and report files modified

Trust subagents to figure out implementation details. Do not over-specify.

### 3. Execute Sequentially

- Run tasks in order, waiting for each to complete
- Track what each task produced for dependent tasks
- Stop on failure

### 4. Aggregate Results

After all tasks complete:
- Run `git diff --stat`
- Compile the list of all modified files
- Summarize work done

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

Include an `affected_repos` array with one entry per repository that had files changed. Each entry must have `repo_path` set to the absolute path of the repository root directory, along with `files_modified` and `git_diff_stat` scoped to that repository.

{
  "files_modified": ["path/to/file1.ext"],
  "git_diff_stat": "<git diff --stat output>",
  "output": "implement-direct",
  "status": "completed",
  "summary": "<summary>",
  "affected_repos": [
    {
      "repo_path": "/absolute/path/to/repo",
      "files_modified": ["relative/path/to/file1.ext"],
      "git_diff_stat": "<git diff --stat output for this repo>"
    }
  ]
}


## Issue Specification

$ARGUMENTS
