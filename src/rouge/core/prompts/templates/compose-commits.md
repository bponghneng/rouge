---
description: ADW step: orchestrates per-repository commit-composition sub-agents, aggregates their results, and returns a JSON summary of conventional commits created.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Compose Commits Orchestrator

Discover all repositories with uncommitted changes, launch a parallel commit-composition sub-agent for each one, and aggregate their results.

## Instructions

### 1. Discover Repositories

The arguments passed to this step are the absolute paths of the repositories to process. Do not perform filesystem discovery — use only the paths provided as arguments.

After receiving the repository paths, filter to only those with uncommitted changes by running `git status --porcelain` in each. A repository has changes if the output is non-empty (covers modified, untracked, and deleted files). Skip any repository with no changes.

### 2. Launch a Sub-Agent per Repository

For each repository with changes, launch a sub-agent using the `Task` tool with:

- The absolute path to the repository as the sole argument
- The following sub-agent prompt (verbatim):

---

You are a commit-composition agent for a single repository. Your working scope is the repository path provided as your argument.

**Instructions**

- Use `cd` to change to the repo directory
- Read current git status: `git status`
- Read current git diff (staged and unstaged changes): `git diff HEAD`
- Read current branch: `git branch --show-current`
- Read recent commits: `git log --oneline -10`

**Commit Process**

#### 1. Group Changes

Logically group related changes into commit units. Consider:

- Functional boundaries (each commit is a complete logical change)
- File relationships (related files usually go together)
- Change types (avoid mixing unrelated features, fixes, or chores)
- Include both staged and unstaged changes; re-stage files as needed to match logical commit groups

#### 2. Compose Commit Messages

For each group, create a conventional commit message:

- Format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
- Keep the first line under 72 characters
- Use imperative mood ("Add" not "Added" or "Adds")
- Include body text for complex changes
- Add `BREAKING CHANGE:` footer if applicable

#### 3. Execute Commits

For each group:

- Stage the relevant files using `git add`
- Commit with the composed message using `git commit -m`

**Output Format**

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

```json
{
  "repo": "<absolute path to this repository>",
  "summary": "<concise summary of the commits>",
  "commits": [
    {
      "message": "<full conventional commit message>",
      "sha": "<commit SHA identifier>",
      "files": ["repo/relative/path1", "repo/relative/path2"]
    }
  ]
}
```

---

Launch all sub-agents in parallel.

### 3. Aggregate Results

After all sub-agents complete, build a `repos` array where each element is one sub-agent's result object.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output": "compose-commits",
  "repos": [
    {
      "repo": "<absolute path to repository>",
      "summary": "<concise summary of commits>",
      "commits": [
        {
          "message": "<full conventional commit message>",
          "sha": "<commit SHA identifier>",
          "files": ["repo/relative/path1", "repo/relative/path2"]
        }
      ]
    }
  ]
}
