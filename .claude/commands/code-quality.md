---
description: Run Rouge code quality tools, fix issues, and re-check until clean
---

# Rouge Code Quality

Run the Rouge repo code quality tools and fix any reported issues. Then respond with the exact `Output Format` below.

## Instructions

### 1. Setup and Context
- Change directory to the project repo: `cd rouge/`
- Ensure dependencies are installed: `uv sync` (only if tools fail due to missing deps)
- Track progress with a short checklist (TODOs in your response) while executing steps

### 2. Backend / Service Code Quality (Rouge)

#### a. Static Analysis

- Run: `uv run mypy src/`
- Fix type errors and re-run until clean

#### b. Unit Tests

- Run: `uv run pytest --cov=src/rouge`
- Fix failing tests and re-run until clean

#### c. Style / Linting

- Run: `uv run ruff check src/`
- If issues are fixable, apply: `uv run ruff check src/ --fix`
- Re-run `uv run ruff check src/` until clean

#### d. Formatting

- Run formatter: `uv run black src/`
- If formatting changed files, re-run `uv run ruff check src/` to ensure style remains clean

### 3. E2E Code Quality

- Not applicable (no separate E2E workspace noted for this repo). Skip.

### 4. Application / Frontend Code Quality

- Not applicable (repo is Python backend/CLI). Skip.

### 5. Final Verification

- Re-run in order: `uv run ruff check src/`, `uv run black src/`, `uv run mypy src/`, `uv run pytest --cov=src/rouge`
- All commands should pass with zero errors

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "issues": [
    {
      "file": "<path to file with issues>",
      "issue": "<description of issues fixed in file>"
    }
  ],
  "output": "code-quality",
  "tools": [
    "uv run ruff check src/",
    "uv run black src/",
    "uv run mypy",
    "uv run pytest tests/ -v"
  ]
}
