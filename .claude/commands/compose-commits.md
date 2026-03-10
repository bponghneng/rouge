---
description: Compose conventional commits from unstaged changes
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Read, Grep
thinking: true
---

# Compose Commits

Examine the repo defined in `Repository` and follow `Instructions` to compose conventional commits from unstaged changes then report the results in the exact format specified `Report`.

## Instructions

- Examine the repo defined in `Repository`. If there is no repo defined, then default to the current directory
- Use `cd` to change to the repo directory if not the current directory
- Use `git status` to examine the current state of the repo
- Use `git diff` to examine the unstaged changes
- Use `git diff --cached` to examine the staged changes
- Use `git branch --show-current` to examine the current branch
- Use `git log --oneline -10` to examine the recent commits
- Read @ai_docs/conventional-commits.md to understand the conventional commits standard
- Based on the git changes shown above, follow the `Commit Process`create meaningful conventional commits

## Commit Process

### 1. Group Changes
Analyze the changes and logically group related modifications that should be committed together. Consider:
- Functional boundaries (each commit should represent a complete logical change)
- File relationships (related files should typically be committed together)
- Change types (don't mix features with fixes unless tightly coupled)

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
1. Stage the relevant files using `git add`
2. Commit with the composed message using `git commit -m`

## Edge Cases

- If no changes exist, report this and exit
- If changes are already staged, unstage them before composing
- If changes span multiple unrelated features, create separate commits

## Report
List all commits created with:
- Full commit message
- SHA hash
- Files included

## Repository

$ARGUMENTS