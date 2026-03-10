# Pull Request / Merge Request Workflow

## Goal

Compose conventional commits from current changes, push branch to `origin`, create PR/MR, and return a human-readable summary containing title, body summary, and commit list.

## Steps

1. Run the compose-commits workflow completely.
2. Draft request metadata:
   - Title: concise overall change summary.
   - Summary: markdown with Description, Type of Change, What Changed, How to Test.
3. Push current branch to `origin` (if not already pushed in this run).
4. Detect platform and create request:
   - GitHub: `gh pr create --title "<title>" --body "<summary>"`
   - GitLab: `glab mr create --title "<title>" --description "<summary>"`
5. Capture resulting PR/MR URL when command succeeds.
6. Return only the PR/MR human-readable summary format from `output-templates.md`.

## Edge Cases

- If platform cannot be determined, stop after push and report manual commands.
- If CLI tool is missing or auth fails, stop after push and report corrective action.
- If PR/MR creation fails, include command output and avoid reporting a created URL.
