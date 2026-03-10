---
name: review-spec
description: Generate a fix-ready specification from unresolved GitHub PR review feedback, including rewrite-aware snapshots for user overrides.
allowed-tools: Bash(gh:*), Bash(uv run .claude/skills/review-spec/scripts/review_spec_cli.py:*), Bash(find:*), Bash(cat:*)
metadata:
  short-description: Generate, rewrite, accept, and merge PR review cycle specs
---

# Review Spec Generator Skill

## When to use

Use this skill when the user asks to convert PR review feedback into an actionable spec, especially for CodeRabbit feedback.

## What this skill does

1. Fetches CodeRabbit review cycles from GitHub PR reviews
2. Extracts only the consolidated section `Prompt for all review comments with AI agents`
3. Parses file path context, line/range hints, and fix instructions
4. Builds per-cycle snapshots with fingerprint-based continuity tracking
5. Classifies status (`resolved`, `unresolved`, `likely_resolved`, `unknown`)
6. Generates one spec per review cycle with unresolved findings
7. Supports per-cycle rewrite, explicit acceptance, and multi-cycle merge into one spec

## Workflow

```
generate → [optional: --rewrite --cycle <id>] → --accept --cycle <id> → --merge <id1>,<id2>
```

After creating a Rouge issue from a merged spec, record it with `--record-issue`.

## Usage

```bash
# Generate specs for all unaddressed review cycles
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94

# Custom output directory
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --output-dir docs/specs

# Override repository path
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --repo-path /absolute/path/to/repo

# Include specific reviewer logins (repeat flag)
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --reviewer coderabbitai --reviewer coderabbitai[bot]

# Rewrite a specific cycle's spec with user decisions
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 \
  --rewrite --cycle 3897858560 \
  --decision "On issue number one, don't fix." \
  --decision "On issue number three, timeout should be 30 seconds."

# Rewrite using directives from a file
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 \
  --rewrite --cycle 3897858560 --decisions-file specs/pr-94-decisions.txt

# Accept a cycle as-is (no rewrite needed)
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 \
  --accept --cycle 3897858560

# Merge two accepted cycles into one spec
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 \
  --merge 3897858560,3901776664

# Record a Rouge issue created from a spec
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 \
  --record-issue --rouge-id ISSUE-123 \
  --spec-path "specs/...-merged-issues-1.md" \
  --cycles 3897858560,3901776664
```

## Requirements

- `gh` installed and authenticated
- Python 3.10+
- `uv`
- PR with unresolved review comments

## Notes

- Primary source is review-body consolidated prompt blocks per cycle.
- Snapshots are stored in `.rouge/review-spec/pr-{number}/snapshots/`.
- Index with per-cycle metadata at `.rouge/review-spec/pr-{number}/index.json`.
- Rouge issue audit log at `.rouge/review-spec/pr-{number}/rouge-issues.json`.
- Thread `isResolved` is used when matching thread evidence exists.
- Safety mode is snapshot-first:
  - keep immutable `original_problem` / `original_fix_instructions`
  - apply user rewrites to `effective_problem` / `effective_fix_instructions`
  - record directive history in snapshot `decisions[]`
- `--rewrite` sets `rewrite_complete: true` on the cycle; does NOT auto-accept.
- `--accept` is the only way to set `accepted: true`; required before `--merge`.

## Output

- Per-cycle spec: `specs/YYYY-MM-DD-HHMMSS-{repo}-pr-{number}-c{cycle_id}-issues-{sequence}.md`
- Merged spec: `specs/YYYY-MM-DD-HHMMSS-{repo}-pr-{number}-merged-issues-{sequence}.md`
- Includes summary counts, issue-by-issue fix instructions, implementation notes, and verification checklist

## References

- `README.md` for detailed usage and troubleshooting
- `scripts/review_spec_cli.py` for implementation details
