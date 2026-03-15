---
description: Compose conventional commits from repo changes and prepare a pull request summary
---

# Compose Commits & PR Summary

Follow the `Instructions` and `Commit Process` to create conventional commits for the repositories described in `README.md`, then respond with the exact `Output Format`.

## Instructions

- Read `README.md` to identify the repository or repositories to process, and process each in turn
- Use `cd` to change to the repo directory if needed
- Read current git status: `git status`
- Read current git diff (staged and unstaged changes): `git diff HEAD`
- Read current branch: `git branch --show-current`
- Read recent commits: `git log --oneline -10`
- Read @ai_docs/conventional-commits.md to follow the conventional commits standard

## Commit Process

### 1. Group Changes
Logically group related changes into commit units. Consider:
- Functional boundaries (each commit is a complete logical change)
- File relationships (related files usually go together)
- Change types (avoid mixing unrelated features, fixes, or chores)
- Include both staged and unstaged changes; re-stage files as needed to match logical commit groups

### 2. Compose Commit Messages
For each group, create a conventional commit message:
- Format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
- Keep the first line under 72 characters
- Use imperative mood ("Add" not "Added" or "Adds")
- Include body text for complex changes
- Add `BREAKING CHANGE:` footer if applicable

### 3. Execute Commits
For each group:
- Stage the relevant files using `git add`
- Commit with the composed message using `git commit -m`

### Edge Cases

- If changes span multiple unrelated features, create separate commits

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output": "pull-request",
  "title": "<clear pull request title summarizing the overall change>",
  "summary": "<markdown in the exact `Summary Format`>",
  "commits": [
    {
      "message": "<full conventional commit message>",
      "sha": "<commit SHA identifier>",
      "files": ["repo/relative/path1","repo/relative/path2"]
    }
  ]
}

### Summary Format

Replace <placeholders> with appropriate details. Select appropriate values for `Type of Change`

```markdown
## Description

<describe the change and any issue fixed. include relevant motivation and context. list and dependencies required for the change.>

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] Chore (non-breaking change for tech debt or devx improvements)
- [ ] Feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] This change requires a documentation update

## What Changed

- <concise summary of change no. 1>
- <concise summary of change no. 2>
- ...

## How to Test

- [ ] <concise description of test no. 1>
- [ ] <concise description of test no. 2>
- [ ] ...
```