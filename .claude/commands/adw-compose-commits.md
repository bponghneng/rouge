---
description: Compose conventional commits from repo changes
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
  "output":"commits",
  "summary":"<concise summary of the commits>",
  "commits":[
    {
      "message":"<full conventional commit message>",
      "sha":"<commit SHA identifier>",
      "files":["repo/relative/path1","repo/relative/path2"]
    }
  ]
}
