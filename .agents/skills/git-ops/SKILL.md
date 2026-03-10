---
name: git-ops
description: 'Run Git commit and PR/MR workflows end-to-end: compose conventional commits, push branches to origin, and create GitHub pull requests or GitLab merge requests. Trigger this skill when users ask for compose commits, commit grouping, pull request creation, merge request creation, branch push automation, or combined "commit + PR/MR" workflows.'
---

# Git Ops Skill

Use this skill for two workflows:

1. Compose commits only.
2. Compose commits and open PR/MR.

Keep behavior deterministic and transparent:

- Follow conventional commit rules.
- Push branch to `origin` at the end of both workflows.
- For PR/MR workflow, detect platform from `origin` remote URL and use `gh` (GitHub) or `glab` (GitLab).
- Return human-readable summaries, not JSON.

Use these files:

- Trigger phrases: `references/triggers.md`
- Commit-only workflow: `references/compose-commits-workflow.md`
- PR/MR workflow: `references/pull-request-workflow.md`
- Platform detection and CLI guardrails: `references/platform-detection.md`
- Output format templates: `references/output-templates.md`

Use `COOKBOOK.md` for compact end-to-end command recipes.
