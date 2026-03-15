---
description: Extract a code review base commit from issue text using a strict, schema-compatible output.
model: sonnet
---

# Review Base Commit Extraction

Read the `Issue Description` below and extract the base commit reference and optional PR/MR number for code review.

## Instructions

- CRITICAL: You are extracting a base commit and an optional PR/MR number.
- Return ONLY valid JSON matching the exact output schema contract.
- Supported base commit patterns only:
  - `review from base commit <git-ref>` (example: `HEAD~3`)
  - `review from <commit-sha>`
  - `Base commit: <commit-sha>`
- `base_commit` must be copied directly from the issue text when a supported pattern exists.
- If the base commit cannot be determined, return `"INVALID"` for `base_commit` and explain the required format in `summary`.
- Supported PR/MR number patterns:
  - `PR #<n>` or `pull request #<n>` → extract `<n>` as an integer for `pr_number`
  - `MR !<n>` or `merge request !<n>` → extract `<n>` as an integer for `pr_number`
- If no PR/MR reference is found, return `null` for `pr_number`.
- No markdown, no code fences, no extra keys, no extra text.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output": "plan",
  "base_commit": "<git-ref-or-sha-or-INVALID>",
  "summary": "<one-sentence rationale>",
  "pr_number": 42
}

Or when no PR/MR is referenced:

{
  "output": "plan",
  "base_commit": "<git-ref-or-sha-or-INVALID>",
  "summary": "<one-sentence rationale>",
  "pr_number": null
}

## Issue Description

$ARGUMENTS
