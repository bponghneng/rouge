---
description: ADW step: runs code quality tools (linters, type checkers, formatters) across the project, applies fixes for reported errors and warnings, and returns a JSON summary of issues resolved.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Code Quality

Discover the available code quality tools in each repository present in the working environment, then run all tools and fix any reported issues. Then respond with the exact `Output Format` below.

## Instructions

### 0. Scope

If repository paths are provided as arguments (`$ARGUMENTS`), restrict all discovery and tool execution to ONLY those directories. Do not scan for additional repositories outside the provided set.

If no arguments are provided, fall back to the current behavior: discover all repositories by locating `.git` folders.

### 1. Discover Repositories and Their Tools

Before running anything, survey the working environment:

- Find all repositories by locating directories that contain a `.git` folder
- For each repo, identify which tools are available by checking config files and lock files:
  - **Python**: `pyproject.toml` or `setup.cfg` → look for `ruff`, `flake8`, `pylint`, `mypy`, `pyright`, `pytest`, `black`, `isort`
  - **JavaScript / TypeScript**: `package.json` scripts → look for `eslint`, `tsc`, `vitest`, `jest`, `prettier`
  - **Elixir**: `mix.exs` → look for `credo`, `dialyxir`, `ex_unit` (`mix test`), `mix format`
  - **PHP**: `composer.json` → look for `phpstan`, `psalm`, `phpcs`, `phpunit`, `php-cs-fixer`
  - **Other**: inspect Makefiles, CI config (`.github/workflows/`, `.gitlab-ci.yml`) for tool invocations
- Record the discovered tools per repo before proceeding. Skip any repo or tool category for which no tooling is configured.

### 2. Run Tools in Order — Linters → Type Checkers → Tests → Formatters

For each discovered repo, run its tools in the following order. Fix issues after each category before moving on.

#### a. Linters

- Run all configured linters for the repo
- Apply auto-fixes where the tool supports them (e.g., `ruff check --fix`, `eslint --fix`)
- Re-run until the linter reports zero errors

#### b. Type Checkers

- Run all configured type checkers for the repo
- Fix type errors and re-run until clean

#### c. Tests

- Run all configured test suites for the repo
- Fix failing tests and re-run until clean

#### d. Formatters

- Run all configured formatters for the repo
- After formatting, re-run linters to confirm style remains clean

### 3. Final Verification

- Re-run all discovered tools for every repo in the same order (linters → type checkers → tests → formatters)
- All commands must pass with zero errors before completing

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
  "tools": ["<each tool command actually run, in execution order>"]
}
