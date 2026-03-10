# Git Ops Cookbook

Detailed operational recipes for `git-ops`.

## Compose commits only

1. Gather context: `git status`, `git diff`, `git diff --cached`, `git branch --show-current`, `git log --oneline -10`.
2. Group file changes into logical commit units.
3. Stage and commit each unit with conventional commits.
4. Push the current branch to `origin`.
5. Return the commit summary format from `references/output-templates.md`.

## Compose commits and open PR/MR

1. Execute the full compose commits workflow.
2. Draft PR/MR title and summary markdown.
3. Ensure branch is pushed to `origin` (if not already done by the compose commits workflow).
4. Detect platform and create review request:
   - GitHub: `gh pr create --title "<title>" --body "<summary>"`
   - GitLab: `glab mr create --title "<title>" --description "<summary>"`
5. Return the PR/MR summary format from `references/output-templates.md`.

## Notes

- If branch has no upstream, use `git push -u origin <branch>`, else `git push`.
- If platform CLI is missing or auth fails, stop after push and report exact follow-up command.
