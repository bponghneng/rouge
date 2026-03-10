# Compose Commits Workflow

<!-- NOTE: A parallel copy of this file exists at
  skills/claude-code/global/git-ops/references/compose-commits-workflow.md
  The duplication is intentional: skills/global/ serves tool-agnostic installs
  while skills/claude-code/global/ is installed specifically for Claude Code.
  Update both files together when the workflow changes. -->

## Goal

Compose conventional commits from current changes, push branch to `origin`, and return a human-readable commit summary.

## Steps

1. Resolve repository path:
   - Use provided path when present.
   - Else use current directory.
2. Gather Git context:
   - `git status`
   - `git diff`
   - `git diff --cached`
   - `git branch --show-current`
   - `git log --oneline -10`
3. Follow conventional commit style (`type(scope): description`).
4. Group files into logical commit units by feature/fix/chore boundaries.
5. For each unit:
   - `git add <files>`
   - `git commit -m "<message>"`
6. Push current branch:
   - If no upstream: `git push -u origin <branch>`
   - Else: `git push`
7. Return only the human-readable commit summary format from `output-templates.md`.

## Edge Cases

- If no changes exist, report no commits created.
- If unrelated changes exist, split into multiple commits.
- If push fails, report the exact error and do not claim success.
