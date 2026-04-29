---
description: ADW step: orchestrates per-repository code quality sub-agents, aggregates their results, and returns a JSON summary of issues resolved.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Code Quality Orchestrator

Discover all repositories in the working environment, launch a parallel code-quality sub-agent for each one, and aggregate their results.

## Instructions

### 1. Discover Repositories

The arguments passed to this step are the absolute paths of the repositories to process. Do not perform filesystem discovery — use only the paths provided as arguments.

After receiving the repository paths, filter to only those with code changes by running `git status --porcelain` in each. A repository has changes if the output is non-empty (covers modified, untracked, and deleted files). Skip any repository with no changes.

### 2. Launch a Sub-Agent per Repository

For each repository with code changes, launch a sub-agent using the `Task` tool with:

- The absolute path to the repository as the sole argument
- The following sub-agent prompt (verbatim):

---

You are a code quality agent for a single repository. Your working scope is the repository path provided as your argument.

**Instructions**

#### 1. Identify Available Tools

Inspect the repository for configured code quality tools:

- **Python**: `pyproject.toml` or `setup.cfg` → look for `ruff`, `flake8`, `pylint`, `mypy`, `pyright`, `pytest`, `black`, `isort`
- **JavaScript / TypeScript**: `package.json` scripts → look for `eslint`, `tsc`, `vitest`, `jest`, `prettier`
- **Elixir**: `mix.exs` → look for `credo`, `dialyxir`, `ex_unit` (`mix test`), `mix format`
- **PHP**: `composer.json` → look for `phpstan`, `psalm`, `phpcs`, `phpunit`, `php-cs-fixer`
- **Other**: inspect Makefiles, CI config (`.github/workflows/`, `.gitlab-ci.yml`) for tool invocations

Skip any tool category for which no tooling is configured.

#### 2. Run Tools in Order — Linters → Type Checkers → Tests → Formatters

##### a. Linters

- Run all configured linters
- Apply auto-fixes where the tool supports them (e.g., `ruff check --fix`, `eslint --fix`)
- Re-run until the linter reports zero errors

##### b. Type Checkers

- Run all configured type checkers
- Fix type errors and re-run until clean

##### c. Tests

- Run all configured test suites
- Fix failing tests and re-run until clean

##### d. Formatters

- Run all configured formatters
- After formatting, re-run linters to confirm style remains clean

#### 3. Final Verification

Re-run all discovered tools in the same order (linters → type checkers → tests → formatters). All commands must pass with zero errors before completing.

**Output Format**

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

```json
{
  "repo": "<absolute path to this repository>",
  "issues": [
    {
      "file": "<path to file with issues>",
      "issue": "<description of issues fixed in file>"
    }
  ],
  "tools": ["<each tool command actually run, in execution order>"]
}
```

---

Launch all sub-agents in parallel.

### 3. Aggregate Results

After all sub-agents complete, build a `repos` array where each element is one sub-agent's result object.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output": "code-quality",
  "repos": [
    {
      "repo": "<absolute path to repository>",
      "issues": [
        {
          "file": "<path to file with issues>",
          "issue": "<description of issues fixed in file>"
        }
      ],
      "tools": ["<each tool command actually run, in execution order>"]
    }
  ]
}
