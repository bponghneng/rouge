---
description: ADW step: reads a CodeRabbit plain-text review and produces a concise markdown summary as JSON, suitable for posting as a PR/MR comment. Accepts the review text as $ARGUMENTS.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Code Review Summary

Read the `CodeRabbit Review` below and produce a concise markdown summary suitable
for posting as a pull-request comment.

## Instructions

- CRITICAL: You are SUMMARISING ONLY. Do not implement fixes, open files, or run tools.
- Read the full review text and identify:
  - The overall verdict (clean / issues found)
  - The most important findings (critical or high-severity issues first)
  - Any recurring themes (e.g. missing error handling, test coverage gaps)
- Write a short, human-friendly markdown summary (no longer than ~200 words).
- Use bullet points for individual findings; lead with a one-sentence verdict.
- Do NOT reproduce the full review text — just summarise it.
- Do NOT include a `<details>` block; the caller appends the full review there.
- Respond exclusively with JSON in the Output Format with zero extra text.
- ABSOLUTELY NO prose, Markdown fences, explanations, or commentary outside the JSON.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output": "code-review-summary",
  "summary": "<concise markdown summary>"
}

## CodeRabbit Review

$ARGUMENTS
