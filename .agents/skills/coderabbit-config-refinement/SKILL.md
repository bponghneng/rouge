---
name: coderabbit-config-refinement
description: Refine and extend CodeRabbit configuration for a target repository with a high-signal, low-noise review strategy. Use when a user wants to tune .coderabbit.yaml, CODING_STANDARDS.md, and optional ast-grep rules based on concrete review-noise issues or loop-count goals.
---

# CodeRabbit Config Refinement

Run this workflow to tune CodeRabbit for higher signal and fewer noisy review loops.

## Target Repo Resolution

1. Resolve the repo from user input and workspace context:

```bash
uv run .claude/skills/coderabbit-config-refinement/scripts/resolve_target_repo.py "$USER_REQUEST" "$PWD"
```

2. If output is `TARGET_REPO=...`, use that path.
3. If output is `MULTIPLE_REPOS`, ask the user to choose one.
4. If output is `NO_REPO_FOUND`, ask user for an explicit repo path.

## Workflow

1. Intake the problem

- Collect explicit pain points: false-positive patterns, noisy severities, loop count, missed critical issues.
- Ask for success criteria: target loop count, acceptable medium/noise level.

2. Baseline audit (read-only)

- Read: `.coderabbit.yaml`, `CODING_STANDARDS.md` (if present), `.coderabbit/rules/` (if present), `.gitignore`.
- Identify overlap in `path_instructions`, broad/noisy tool settings, and missing severity guidance.

3. Codify policy

- Create or update `CODING_STANDARDS.md` at repo root.
- Include: purpose, severity model (`CRITICAL`, `HIGH`, `MEDIUM/LOW`), core standards, automated rule interpretation.
- Keep policy focused on consequential defects; de-emphasize style-only concerns.

4. Refactor `.coderabbit.yaml`

- Set `reviews.profile: chill` unless user requests stricter behavior.
- Add severity-first `tone_instructions` and require actionable fixes.
- Use non-overlapping `path_instructions` by subsystem.
- Keep `auto_incremental_review: true`; tune `auto_pause_after_reviewed_commits` to user goal (default 8 for loop control).
- Scope knowledge base guidelines to `CODING_STANDARDS.md`.

5. Tool tuning

- Keep only high-signal tools for the repo.
- React Native default: keep `eslint` + `gitleaks`; disable low-value extras unless requested.
- Elixir/Phoenix default: keep `gitleaks`; add `ast-grep` only for narrow high-confidence rules.

6. Optional AST rules (narrow first)

- Add `reviews.tools.ast-grep` and `rule_dirs` only if needed.
- Start with 1-3 deterministic `CRITICAL/HIGH` rules.
- Avoid broad keyword-only matching.
- Add `.coderabbit/rules/README.md` with scope, rationale, and tuning guidance.

7. Housekeeping

- Ensure `.coderabbit.yaml` is tracked (remove from `.gitignore` if ignored).
- Keep file naming and locations consistent across repos.

8. Final tightening pass

- Remove redundant/overlapping instructions.
- Tighten patterns that are likely noisy.
- Verify standards, config, and rules are consistent.

9. Deliverable summary

- Report what changed, why, and expected signal/noise impact.
- List follow-up test-loop metrics to collect (issue count by severity, false positives, loop count).

## Decision Points to Walk Through with User

Use these decisions when requirements are not explicit:

1. Severity strictness: `CRITICAL/HIGH` only vs include selected `MEDIUM`.
2. Auto-review loop control: set `auto_pause_after_reviewed_commits` (recommended starting point: 8).
3. Tool scope: minimal high-signal toolset vs broader static checks.
4. AST rules: enable now with narrow security/correctness rules vs defer until baseline loop data is collected.
5. Path instruction depth: coarse by top-level modules vs detailed per subsystem.

## Acceptance Checklist

- `.coderabbit.yaml` emphasizes consequential defects and minimizes style noise.
- `path_instructions` are non-overlapping and repository-specific.
- `CODING_STANDARDS.md` exists and is referenced by knowledge base settings.
- Any AST rules are narrow, documented, and high-confidence.
- `.gitignore` does not accidentally block the active CodeRabbit config.
