---
name: consensus-review
description: Runs a multi-agent consensus code review. Use when reviewing code changes, before pushing a PR, or as the review step in a development workflow. Spawns three independent reviewers (standards-reviewer, correctness-reviewer, architecture-reviewer) in parallel, then passes their outputs to review-synthesizer for a tiered consensus report with a 1-100 quality score. Accepts an optional plan file; when provided, reviewers also check for plan divergences. Scope defaults to all local changes (staged, unstaged, and untracked); also accepts a base commit SHA, branch diff, or explicit file list.
---

# Consensus Review

Orchestrates three independent reviewer agents and one synthesis agent to produce a stable, tiered consensus review. When a plan file is provided, the review also checks for divergences between the implementation and the plan.

## Prerequisites

All six agents must be present in `.claude/agents/`:
- `standards-reviewer`, `correctness-reviewer`, `architecture-reviewer` — workspace-specific reviewers
- `review-synthesizer` — workspace-agnostic synthesizer
- `consensus-review-poster` — workspace-agnostic PR comment poster
- `consensus-review-fixer` — workspace-agnostic fix agent

If any are missing, generate them using the `/meta-consensus-review-agents` command.

## Inputs Required

1. **PR/MR number** (optional) — if provided, the diff is fetched from the platform rather than from local git. Triggers comment posting and audit trail persistence after review.
2. **Plan file** (optional) — path to the implementation plan the code was built against. If not provided, reviewers evaluate intrinsic code quality only; plan conformance checks are skipped.
3. **Code changes** — specify the scope as one of:
   - *(default)* All local changes: staged, unstaged, and untracked files
   - A base commit SHA to compare the working tree against
   - A branch diff
   - An explicit file list

## Steps

### Step 0 — Recover prior cycle context (PR/MR number only)

If the trigger includes a PR or MR number, run the context recovery script **before** doing anything else:

```bash
uv run .agents/skills/consensus-review/scripts/recover_context.py <number>
```

The script reads `DEV_SEC_OPS_PLATFORM` from `.env` at the workspace root to determine whether the repository is hosted on GitHub (`pr-` prefix) or GitLab (`mr-` prefix), and looks up the audit trail directory accordingly. If `.env` is absent the platform defaults to `github`. Override with `--platform github|gitlab` if needed (e.g. `uv run ... 161 --platform gitlab`).

Read the full output. It tells you:
- The **platform** and **log directory path** — use `LOG_DIR` from this output for the rest of the skill; do not recompute it
- The **next cycle number** — use this as `CYCLE`; do not recompute it
- The **plan file path** — use this instead of asking the user for one; skip the "no plan file" notice if it is present
- **Prior cycle summaries** — a concise history of what each prior cycle found
- **Operator-accepted findings** — items the operator explicitly accepted in a prior cycle; pass these to the synthesizer so it does not re-raise them

If the log directory does not yet exist (first cycle), the script still outputs `CYCLE = 01` and a note that no prior context exists. Continue normally.

---

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

---

**Log directory setup (PR/MR number only)**

If a PR/MR number was given, set up the audit trail directory now.

Use `LOG_DIR` and `CYCLE` from the Step 0 script output — do not recompute them. The directory prefix (`pr-` for GitHub, `mr-` for GitLab) was already resolved by the script from `DEV_SEC_OPS_PLATFORM`.

```bash
mkdir -p "$LOG_DIR"
```

If `CYCLE > 1`, check whether the prior cycle's fix log exists (`fix-{CYCLE-1:02d}.md`). If it is missing, note this to the user as informational — the fixer was not run for that cycle. Do not block.

If `CYCLE == 1` and a plan file was provided, copy it to the log directory:

```bash
cp <plan-file-path> "$LOG_DIR/plan.md"
```

If no PR/MR number was given, skip log directory setup entirely — local reviews are not persisted.

### Step 2 — Run three reviewers in parallel

Spawn all three reviewer agents simultaneously using the Agent tool. Run all three calls in a single response — do not wait for one to complete before starting the others.

Each agent receives a prompt containing the code diff, and the plan document when one was provided.

Agents to invoke (by subagent_type):
- `standards-reviewer`
- `correctness-reviewer`
- `architecture-reviewer`

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

Once all three reviewer outputs are returned, invoke `review-synthesizer` with a prompt containing all three reviewer outputs in full, clearly labeled, plus the log directory and cycle number when available:

```
## standards-reviewer Output

[Full standards-reviewer output]

---

## correctness-reviewer Output

[Full correctness-reviewer output]

---

## architecture-reviewer Output

[Full architecture-reviewer output]

---

## Review History

Log directory: [LOG_DIR or "none"]
Current cycle: [CYCLE or "none"]

[If CYCLE > 1: paste the full output from recover_context.py here, including
prior cycle summaries and operator-accepted findings. The synthesizer uses this
to suppress re-raised accepted findings and to calibrate findings against the
pattern of prior cycles.]
```

### Step 4 — Persist review and output

**If a PR/MR number was given:** write the synthesizer output to `{LOG_DIR}/review-{CYCLE:02d}.md`.

**If no PR/MR number was given:** present the synthesizer's output directly to the user without summarizing or modifying it. Stop here.

### Step 5 — Post comment (PR/MR number given)

Invoke the `consensus-review-poster` agent with a prompt containing:
- The review file path: `{LOG_DIR}/review-{CYCLE:02d}.md`
- The PR/MR number
- The log directory: `{LOG_DIR}`
- The cycle number: `{CYCLE}`
- The repo dir (the git repo root where `gh`/`glab` commands should run — defaults to `.`, but must be set to the repo's root directory whenever the skill is invoked from a workspace folder that is not itself a git repo, e.g. the workspace root contains `rouge/` as a subdirectory)
- The skill dir: the path to this skill's directory containing `scripts/post_review_comment.py`

The `consensus-review-poster` agent owns clean/not-clean determination, summary authorship, and script invocation. Do NOT perform any of those steps in this session.

Report the outcome returned by the `consensus-review-poster` agent (success or failure, and the PR/MR comment URL if available).

### Step 6 — Fix issues (optional)

If the user asks to fix the review issues after the comment is posted (e.g. "fix the issues", "run the fixer", "fix all findings"):

**Always use the `consensus-review-fixer` agent for all fixes — do not apply fixes manually in this session.**

Invoke the `consensus-review-fixer` agent with a prompt containing:
- The review file path: `{LOG_DIR}/review-{CYCLE:02d}.md`
- The log directory: `{LOG_DIR}`
- The cycle number: `{CYCLE}`

Report the outcome returned by the `consensus-review-fixer` agent (how many findings were addressed, accepted/skipped, and any uncertainties).
