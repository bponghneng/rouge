# Platform Detection and Guardrails

## Platform Detection

1. Read origin URL:
   - `git remote get-url origin`
2. Determine platform:
   - Contains `gitlab` -> `gitlab`
   - Contains `github` -> `github`
   - Otherwise -> `unknown`

## CLI Preconditions

- GitHub flow:
  - `command -v gh`
  - `gh auth status`
- GitLab flow:
  - `command -v glab`
  - `glab auth status`

If checks fail, do not attempt PR/MR creation. Push branch only, then report what is missing and the manual command to run.

## Push Rules

- Determine current branch with `git branch --show-current`.
- If upstream missing, push with `git push -u origin <branch>`.
- Otherwise push with `git push`.
