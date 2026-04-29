---
description: ADW step: orchestrates per-repository PR-composition sub-agents for provided repository paths, grouping changes into conventional commits and preparing PR titles and descriptions, then aggregates results as JSON.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Pull Request Orchestrator

Use the repository paths provided as arguments, launch a parallel PR-composition sub-agent for each repository with changes, and aggregate their results.

## Instructions

### 1. Select Target Repositories

The arguments passed to this step are the absolute paths of the repositories to process. Do not perform filesystem discovery, search for repositories, or infer additional repository paths — use only the paths provided as arguments.

After receiving the repository paths, filter to those with either uncommitted changes (`git status --porcelain` output is non-empty) or commits ahead of the remote base branch (`git rev-list --count origin/HEAD..HEAD` output is greater than 0). This ensures that re-runs after commits are already created will still process repositories correctly.

### 2. Launch a Sub-Agent per Repository

For each repository with changes, launch a sub-agent using the `Task` tool with:

- The absolute path to the repository as the sole argument
- The following sub-agent prompt (verbatim):

---

You are a PR-composition agent for a single repository. Your working scope is the repository path provided as your argument.

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

#### 4. Compose PR Title and Summary

After all commits are created, compose a pull request title and summary:

- Title: clear, concise summary of the overall change (under 72 characters)
- Summary: structured markdown using the format below

**Summary Format**

```markdown
## Description

<describe the change and any issue fixed; include relevant motivation and context>

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] Chore (non-breaking change for tech debt or devx improvements)
- [ ] Feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] This change requires a documentation update

## What Changed

- <concise summary of change no. 1>
- <concise summary of change no. 2>

## How to Test

- [ ] <concise description of test no. 1>
- [ ] <concise description of test no. 2>
```

**Output Format**

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

```json
{
  "repo": "<absolute path to this repository>",
  "title": "<clear pull request title summarizing the overall change>",
  "summary": "<markdown in the Summary Format above>",
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
  "output": "pull-request",
  "repos": [
    {
      "repo": "<absolute path to repository>",
      "title": "<pull request title>",
      "summary": "<markdown PR summary>",
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
