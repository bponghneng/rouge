---
name: rouge
description: Use the Rouge CLI to manage issues, run workflows, and inspect step/artifact state. Trigger this skill when the user asks to run or explain `rouge` commands such as `rouge issue create`, `rouge workflow run`, `rouge workflow patch`, `rouge workflow codereview`, `rouge step ...`, `rouge artifact ...`, or `rouge reset`.
---

# Rouge CLI Skill

Run `rouge` from the directory that contains the `.env` file you want Rouge to load (typically a workspace root), not from nested project subdirectories unless that is where `.env` lives. The `.env` file must have values for `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` for `rouge` to function properly.

Use paths (for example `--spec-file`) relative to that same directory.

## Environment setup

Use `sync_env.py` to synchronize `.env` with the current Rouge template after a Rouge update. It rewrites `.env` from the template's current variable set, merging in any values you already have, and reports which keys were preserved, dropped, or added.

```bash
# Sync using defaults (template: ~/git/rouge/rouge/.env.example, target: .env, backup: .env.old)
uv run .claude/skills/rouge/scripts/sync_env.py

# Specify paths explicitly
uv run .claude/skills/rouge/scripts/sync_env.py \
  --template ~/git/rouge/rouge/.env.example \
  --target .env \
  --backup .env.old
```

Check the output for `dropped keys count > 0` — those variables were removed from the Rouge template and are no longer used.

## Creating a code review issue

Derive the base commit first, then create the issue with `--type codereview`.
The issue description MUST include the phrase `Base commit: <sha>` so that
ReviewPlanStep can identify the commit reference when the workflow runs.

### From a GitHub PR

```bash
BASE=$(gh pr view <number> --json baseRefOid --jq '.baseRefOid')
BASE_BRANCH=$(gh pr view <number> --json baseRefName --jq '.baseRefName')
TITLE=$(gh pr view <number> --json title --jq '.title')
rouge issue create \
  "Code review for PR #<number>: $TITLE. Base commit: $BASE" \
  --title "codereview: PR #<number> $TITLE" \
  --branch "$BASE_BRANCH" \
  --type codereview
```

### From a GitLab MR

```bash
DATA=$(glab mr view <number> --output json)
BASE=$(echo "$DATA" | jq -r '.diff_refs.base_sha')
BASE_BRANCH=$(echo "$DATA" | jq -r '.target_branch')
TITLE=$(echo "$DATA" | jq -r '.title')
rouge issue create \
  "Code review for MR !<number>: $TITLE. Base commit: $BASE" \
  --title "codereview: MR !<number> $TITLE" \
  --branch "$BASE_BRANCH" \
  --type codereview
```

### From N recent commits on a branch

```bash
BASE=$(git -C $REPO_PATH rev-parse <branch>~<N>)
rouge issue create \
  "Code review for last <N> commits on <branch>. Base commit: $BASE" \
  --title "codereview: <branch> last <N> commits" \
  --branch "<branch>" \
  --type codereview
```

## Command reference

Use `references/commands.md` for the full command syntax covering issue management, workflow execution, reset, step operations, artifact operations, and comment operations.
