---
name: consensus-review
description: Runs a multi-agent consensus code review. Use when reviewing code changes, before pushing a PR, or as the review step in a development workflow. Spawns three independent reviewers (adw-standards-reviewer, adw-correctness-reviewer, adw-architecture-reviewer) in parallel, then passes their outputs to adw-review-synthesizer for a tiered consensus report with a 1-100 quality score. Accepts an optional plan file; when provided, reviewers also check for plan divergences. Scope defaults to all local changes (staged, unstaged, and untracked); also accepts a base commit SHA, branch diff, or explicit file list.
---

# Consensus Review

Orchestrates three independent reviewer agents and one synthesis agent to produce a stable, tiered consensus review. When a plan file is provided, the review also checks for divergences between the implementation and the plan.

## Prerequisites

The three reviewer agents (`adw-standards-reviewer`, `adw-correctness-reviewer`, `adw-architecture-reviewer`) and the synthesizer (`adw-review-synthesizer`) must be present in `.claude/agents/`. If they are not present, generate them using the `/meta-consensus-review-agents` command.

## Inputs Required

1. **PR/MR number** (optional) — if provided, the diff is fetched from the platform rather than from local git. Triggers comment posting after review.
2. **Plan file** (optional) — path to the implementation plan the code was built against. If not provided, reviewers evaluate intrinsic code quality only; plan conformance checks are skipped.
3. **Code changes** — specify the scope as one of:
   - *(default)* All local changes: staged, unstaged, and untracked files
   - A base commit SHA to compare the working tree against
   - A branch diff
   - An explicit file list

## Steps

### Step 1 — Gather inputs

Determine the code scope using the following priority ladder. Check each level in order and use the first match.

**Priority 1 — PR/MR number given**

If the trigger includes a PR or MR number (e.g. "run consensus-review for PR 116"):

1. Read `DEV_SEC_OPS_PLATFORM` from `.env` at the workspace root.
2. Fetch the diff using the appropriate command:
   - `github`: `gh pr diff <number>`
   - `gitlab`: `glab mr diff <number>`
3. Use the fetched diff as the full code scope.
4. Skip all git diff commands — do not run any of the steps below.

**Priority 2 — Base commit SHA given**

```bash
git diff <sha>                            # all changes since that commit
git ls-files --others --exclude-standard  # untracked files
```

Read the full content of each untracked file and include it in the diff passed to reviewers, labeled clearly as a new file.

**Priority 3 — Branch diff given**

Use the appropriate `git diff` range for that branch.

**Priority 4 — Explicit file list given**

Diff only those files using `git diff -- <file1> <file2> ...`.

**Priority 5 — Default (nothing specified)**

```bash
git diff HEAD                             # staged + unstaged changes to tracked files
git ls-files --others --exclude-standard  # untracked files
```

Read the full content of each untracked file and include it in the diff passed to reviewers, labeled clearly as a new file.

If no changes are found at Priority 5 (empty diff and no untracked files), ask the user to clarify scope (base SHA, branch, or file list).

---

If a plan file path was provided, read it in full. If no plan file was provided, notify the user before proceeding:

> **Note:** No plan file provided. Reviewing changes for intrinsic quality only — plan conformance checks will be skipped.

### Step 2 — Run three reviewers in parallel

Spawn all three reviewer agents simultaneously using the Agent tool. Run all three calls in a single response — do not wait for one to complete before starting the others.

Each agent receives a prompt containing the code diff, and the plan document when one was provided.

Agents to invoke (by subagent_type):
- `adw-standards-reviewer`
- `adw-correctness-reviewer`
- `adw-architecture-reviewer`

When a plan file is provided, construct each prompt as:

```
## Plan

[Full plan document]

---

## Code Changes

[Full code diff]
```

When no plan file is provided, construct each prompt as:

```
## Code Changes

[Full code diff]
```

### Step 3 — Synthesize

Once all three reviewer outputs are returned, invoke `adw-review-synthesizer` with a prompt containing all three reviewer outputs in full, clearly labeled:

```
## adw-standards-reviewer Output

[Full adw-standards-reviewer output]

---

## adw-correctness-reviewer Output

[Full adw-correctness-reviewer output]

---

## adw-architecture-reviewer Output

[Full adw-architecture-reviewer output]
```

### Step 4 — Output (no PR/MR number)

If no PR/MR number was given in the trigger, present the synthesizer's output directly to the user without summarizing or modifying it.

### Step 5 — Post comment (PR/MR number given)

If a PR/MR number was given in the trigger:

1. Write the synthesizer output to a temporary file at `/tmp/consensus-review-output.txt`.

2. If the review is **not clean** (i.e. the synthesizer output contains any of: CRITICAL, HIGH, MEDIUM, LOW, nitpick, or a score below 8/10), generate a bullet summary now, inline in this session:

   - Write 3–6 short markdown bullet lines summarizing the major themes, affected areas, and what needs follow-up.
   - Start every line with `- `.
   - Do not include headings, code blocks, or long quotes.
   - Write the bullet lines to `/tmp/consensus-review-summary.txt`.

3. Run the post-comment script, passing the repo directory where `gh`/`glab` should run:

   **When the review has issues (summary file was generated in step 2):**
   ```bash
   uv run .claude/skills/consensus-review/scripts/post_review_comment.py \
     --pr-number <number> \
     --review-file /tmp/consensus-review-output.txt \
     --repo-dir <path-to-git-repo> \
     --summary-file /tmp/consensus-review-summary.txt
   ```

   **When the review is clean (no issues found):**
   ```bash
   uv run .claude/skills/consensus-review/scripts/post_review_comment.py \
     --pr-number <number> \
     --review-file /tmp/consensus-review-output.txt \
     --repo-dir <path-to-git-repo>
   ```

`--repo-dir` defaults to `.` if omitted, but must be set to the repo's root directory whenever the skill is invoked from a workspace folder that is not itself a git repo (e.g. the workspace root contains `rouge/` as a subdirectory).

**Important:** The script owns all comment body construction — the summary bullets and the collapsible `<details>` accordion around the full review output. Do NOT construct a comment body manually or post output directly via `gh`/`glab`. If the script exits non-zero, report the error message to the user and stop.

4. Do NOT print the synthesizer output to the user. Instead, report whether the comment was posted successfully or failed, and include the PR/MR comment URL if available.
