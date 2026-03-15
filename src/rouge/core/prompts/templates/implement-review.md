---
description: ADW step: processes an automated review report (e.g. CodeRabbit plain-text) issue by issue, applying simplicity-first fixes or deferring large changes to a plan file. Returns a JSON report of actions taken per issue.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Work Through Automated Review Issues

Use the automated review report below to drive a focused round of fixes or follow-up plans in the project repository.

## Instructions

- Treat `$ARGUMENTS` as the full plain-text report produced by an automated reviewer (for example, CodeRabbit in plain text mode).
- Apply the workflow rules and simplicity-first guidelines from the project repo's `CLAUDE.md` (see `CLAUDE.md` and `README.md` to locate the repo root):
  - Research first, then propose, then implement.
  - Prefer the smallest coherent change that solves each issue.
  - Respect existing patterns and conventions in the codebase.
- Do not blindly apply suggestions; always verify them against the actual code, specs, and project documentation.
- When a change would be large or architecture-impacting, prefer to create or update a plan under `specs/` instead of implementing it directly, and clearly mark that issue as deferred in your report.

## Parsing the Review Report

- The report is organized into sections separated by `=====` lines.
- For each section, extract the following fields:
  - **File**: path after `File:` (for example, `some/dir/file.ext`).
  - **Line range**: text after `Line:` (for example, `18 to 26`).
  - **Type**: value after `Type:` (for example, `potential_issue`).
  - **Prompt**: any text that appears after `Prompt for AI Agent:` up to the next blank line or section separator. This may be empty or missing.
- Treat each `File` section as a separate issue, even if multiple issues refer to the same file.

## Per-Issue Workflow

Process issues strictly in the order they appear in the report.

For each issue:

1. **Gather context**
   - Open the referenced file and inspect the indicated line range plus nearby context.
   - If a `Prompt for AI Agent` is present and non-empty, treat it as the primary instruction.
   - If the prompt is missing or empty, infer the concern from the code or spec around the referenced lines.
2. **Decide approach**
   - Decide whether this issue can be addressed as a **small, local change** that fits within the existing architecture.
   - If the issue implies a broader refactor, significant schema change, or spec overhaul:
     - Do not implement it directly.
     - Instead, create or update an implementation plan in the repo's planning/specs area (using the project's preferred bug/chore plan formats) and mark this issue as `needs-followup` in your report.
3. **Propose the change**
   - Before editing files, briefly describe the intended change (what and why) in your working notes for this issue. This satisfies the “discuss before implementing” expectation.
   - Ensure the proposal is consistent with:
     - `AGENTS.md` (simplicity-first, minimal dependencies).
     - Any relevant project docs such as the `README.md`, implementation guides, and planning/specs documents.
4. **Implement small, clear fixes**
   - For issues classified as small and well-understood:
     - Apply the minimal code or spec change that resolves the issue.
     - Keep changes tightly scoped to the referenced behavior; avoid unrelated refactors.
     - When the issue concerns specs or design docs, update the specification text and examples consistently.
     - When the issue concerns executable code, ensure changes compile and match existing style.
   - Update or add tests/docs if that is necessary to keep the change safe and understandable.
5. **Validation**
   - When practical, run targeted validation appropriate to the area you touched (for example, relevant linters or tests).
   - At minimum, re-read the changed code/spec to ensure it is internally consistent and does not obviously break existing behavior.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "issues": [
    {
      "file": "<referenced file path>",
      "lines": "<referenced line range>",
      "type": "<issue type from report>",
      "status": "<fixed|skipped|needs-followup>",
      "notes": "<brief explanation of the action or decision>"
    }
  ],
  "output": "implement-review",
  "summary": "<concise summary of actions taken>"
}

## Automated Review Report

$ARGUMENTS
