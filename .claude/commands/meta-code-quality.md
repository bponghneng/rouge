---
description: Generate a workspace-specific code-quality skill for multiple repositories
---

# Meta Code Quality Skill Generator

Generate a custom `/code-quality` skill tailored to your workspace's repository structure and code quality tooling.

## Instructions

### 1. Discover All Repositories in Workspace

First, discover all Git repositories in the workspace by finding top-level directories containing `.git/`:

```bash
find . -maxdepth 2 -name ".git" -type d | sed 's|/\.git||' | sed 's|^\./||'
```

This will list all repository directories (e.g., `repo1/`, `repo2/`, `repo3/`).

### 2. Discover Available Code Quality Commands Per Repository

For each discovered repository, inspect common configuration files to identify available code quality commands. Prefer file-driven discovery over environment checks.

**Python Projects** (check `pyproject.toml`, `setup.py`, `tox.ini`, `Makefile`):

```bash
cd <repo-path>
# Look for tool configuration and common script blocks
rg -n "\[tool\.(ruff|mypy|pytest|black|isort|hatch|tox)\]|\[project\.scripts\]|\[tool\.hatch\.envs" pyproject.toml 2>/dev/null
```

**Node.js/JavaScript Projects** (check `package.json`):

```bash
cd <repo-path>
# Extract scripts from package.json (best-effort)
rg -n '"scripts"' package.json 2>/dev/null
```

**Elixir Projects** (check `mix.exs` and `mix.lock`):

```bash
cd <repo-path>
rg -n "credo|dialyzer|ex_unit|formatter" mix.exs 2>/dev/null
```

**Makefile-based Projects**:

```bash
cd <repo-path>
# Extract likely quality targets from Makefile
rg -n '^(test|lint|format|check|quality)[^:]*:' Makefile 2>/dev/null
```

Use the discovered config sections to infer the full runnable commands (e.g., `uv run ruff check src/` from a `[tool.ruff]` section, `npm run lint` from a `package.json` script). Normalize into a command list per repository, organized by:
- Command category (Static Analysis, Tests, Linting, Formatting, Build)
- Command name or script (e.g., `uv run pytest`, `npm run lint`)
- Source file (e.g., from `package.json` scripts, `pyproject.toml`, `Makefile`)

### 3. Generate the Skill File

Using the gathered information, create a new file at:
`.codex/prompts/code-quality.md`

The file should follow this structure:

```markdown
---
description: Run code quality tools across all workspace repositories, fix issues, and re-check until clean
---

# Code Quality - <Workspace Name>

Run code quality tools across all repositories in the workspace and fix any reported issues. Then respond with the exact `Output Format` below.

## Instructions

### Arguments

- If `$ARGUMENTS` is provided, treat it as a space-separated list of repository paths to run
- If `$ARGUMENTS` is empty, run commands for all discovered repositories

### 1. Setup and Context

- Track progress with a short checklist (TODOs in your response) while executing steps
- Process repositories in sequence, completing all checks for one before moving to the next
- If any command fails due to missing dependencies, install them first

### 2. Repository: <repo-1-path>

IMPORTANT: Run only when `$ARGUMENTS` includes the <repo-1-path> repo or when `$ARGUMENTS` is empty

#### a. <Category 1 Name>
- Change directory: `cd <repo-1-path>`
- Run: `<command-1>`
- Fix any issues and re-run until clean
- <Additional instructions if needed>

#### b. <Category 2 Name>
- Run: `<command-2>`
- Fix any issues and re-run until clean
- <Additional instructions if needed>

[Repeat for all categories in repo-1]

#### Final Verification (<repo-1-path>)
- Re-run all commands in order to ensure everything passes
- All commands should pass with zero errors

### 3. Repository: <repo-2-path>

IMPORTANT: Run only when `$ARGUMENTS` includes the <repo-2-path> repo or when `$ARGUMENTS` is empty

[Repeat structure from section 2 for each repository]

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "repositories": [<repository code quality summary using the exact `Repository Summary` format>],
  "output": "code-quality",
  "workspace": "<workspace-name>"
}
```

### Repository Summary

```json
{
  "path": "<repository path>",
  "issues": [
    {
      "file": "<path to file with issues>",
      "issue": "<description of issues fixed in file>"
    }
  ],
  "tools": [
    "tool-1",
    "tool-2",
    ...
  ]
}
```

### 4. Customization Guidelines

When generating the skill, ensure:

1. **Repository-Specific Paths**: Each repository section should start with `cd <repo-path>` to ensure commands run in the correct directory

2. **Dependency Installation**: Include conditional dependency installation instructions (e.g., `uv sync`, `npm install`) only when tools fail

3. **Command Ordering**: Order discovered quality commands consistently for every repository:
   - Static analysis and type checking first
   - Tests second
   - Linting next (auto-fix command before non-fix lint command when available)
   - Formatting last
   - Build verification can be included where applicable, but still place formatting last

4. **Fix-and-Rerun Pattern**: Each command should have clear instructions to fix issues and re-run until clean

5. **Auto-Fix Commands**: When linters/formatters have auto-fix capabilities (e.g., `ruff check --fix`, `npm run lint --fix`), include those instructions

6. **Final Verification**: Include a final verification step per repository that re-runs all commands in sequence

7. **JSON Output Schema**: Use a top-level output object with a `repositories` array and define a separate `Repository Summary` schema that each entry must follow

8. **Repository Argument Gating**: Add the same `IMPORTANT` gating note to every repository section so each repo runs only when selected by `$ARGUMENTS` or when `$ARGUMENTS` is empty

### 5. Installation and Usage

After generating the skill file:

1. Save it to the appropriate location in the workspace
2. Inform the user the skill is ready and can be invoked with `/code-quality`
3. Provide a brief summary of what repositories and tools are covered

### Example Interaction

**User invokes with no arguments**

**Assistant**:
1. Discovers repositories: `repo1/`, `repo2/`, `repo3/`
2. Discovers commands in each repository
3. Generates the skill file using the discovered commands

**Invocation examples after generation**

- `/code-quality` (runs all repositories)
- `/code-quality repo1/ repo2/` (runs only `repo1/` and `repo2/`)

## Notes

- The meta-skill only generates the configuration file; it does not execute code quality checks
- Always discovers all Git repositories in the workspace (top-level directories with `.git/`)
- **Always discovers available code quality commands** by inspecting project configuration files:
  - Python: `pyproject.toml`, `setup.py`, `tox.ini`, `Makefile`
  - Node.js: `package.json` scripts section
  - Elixir: `mix.exs`, `mix.lock`
  - Generic: `Makefile` targets
- Repositories and commands are always auto-discovered and used to generate the skill
- The generated `/code-quality` skill accepts an optional space-separated repo list via `$ARGUMENTS`, or runs all repositories when empty
- The generated skill should be committed to version control for team consistency
