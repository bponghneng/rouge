# Review Spec Generator

Generate structured specification documents from unresolved GitHub PR review comments.

## Overview

The Review Spec Generator is a skill that automates extraction and organization of CodeRabbit feedback from GitHub pull requests. It reads CodeRabbit review cycles, parses the consolidated AI prompt block for each cycle, and generates a fix-ready specification.

### Why Use This Skill?

**Problem it solves:**
- CodeRabbit provides detailed AI-generated review feedback with actionable prompts
- Manually extracting and organizing these comments is time-consuming
- AI coding agents need structured specifications to implement fixes efficiently
- Tracking resolution status across multiple issues is difficult

**Value it provides:**
- Automated extraction of unresolved review issues
- Structured organization by severity
- Ready-to-use AI Agent Prompts
- Clear verification checklist
- Seamless integration with AI coding workflows

## Prerequisites

### Required Tools

1. **GitHub CLI (`gh`)**
   ```bash
   # Install (macOS)
   brew install gh

   # Authenticate
   gh auth login
   ```

2. **Python 3.10+**
   ```bash
   python --version
   # Should show 3.10 or higher
   ```

3. **uv (Python package manager)**
   ```bash
   # Install
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

### Repository Requirements

- Must be a GitHub repository
- Must have CodeRabbit installed and configured
- PR must have unresolved review comments (CodeRabbit by default)

## Configuration

### Workspace Setup

For workspace setups (where the git repository is in a subdirectory), configure the repository path in your workspace root `.env` file:

```bash
# .env at workspace root
REPO_PATH=/absolute/path/to/repository
WORKING_DIR=/absolute/path/to/workspace
```

**Example:**
```bash
# Workspace structure:
# ~/git/vault/          <- workspace root
# ~/git/vault/.env      <- contains REPO_PATH
# ~/git/vault/vault/    <- actual git repository

# In ~/git/vault/.env:
REPO_PATH=/Users/username/git/vault/vault
```

**Requirements:**
- `REPO_PATH` must be an absolute path
- Path must point to a directory containing a `.git` subdirectory
- If `REPO_PATH` is not set, script defaults to current working directory
- If `WORKING_DIR` is not set, output defaults to current working directory

**Override via CLI:**
```bash
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --repo-path /path/to/repo
```

### Environment File

Copy `.env.example` to your workspace root `.env` and configure:

```bash
cp .claude/skills/review-spec/.env.example .env
# Edit .env and set REPO_PATH to your repository's absolute path
```

## Installation

This skill is installed via the vault installer:

```bash
cd /path/to/vault
uv run scripts/install-coders.py <project-name>
```

The skill will be symlinked to `.claude/skills/review-spec/` in the target project.

## Usage

### Via Skill Command

```
/review-spec 94
```

Replace `94` with your PR number.

### Via Narrative

```
Generate a specification from PR #94 review comments
```

Claude will recognize the intent and invoke the skill.

### Direct Script Execution

```bash
# From workspace root (auto-detects REPO_PATH from .env)
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94

# With custom output directory
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --output-dir docs/specs

# Override repository path
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --repo-path /absolute/path/to/repo

# Include specific reviewer accounts (repeat --reviewer)
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --reviewer coderabbitai --reviewer coderabbitai[bot]

# Rewrite latest snapshot with user decisions (skip/override)
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --rewrite \
  --decision "On issue number one, don't fix." \
  --decision "On issue number three, timeout should be 30 seconds."

# Rewrite using directives from a file
uv run .claude/skills/review-spec/scripts/review_spec_cli.py 94 --rewrite --decisions-file specs/pr-94-decisions.txt
```

## Output

### File Location

By default, the spec is generated at:
```
specs/YYYY-MM-DD-HHMMSS-{repo}-pr-{number}-issues-{sequence}.md
```

Example for `rouge` PR `136`:
```
specs/2026-02-21-061600-rouge-pr-136-issues-1.md
specs/2026-02-21-065100-rouge-pr-136-issues-2.md
```

### Spec Structure

```markdown
# Code Review: Address PR #{number} Review Issues

**Repository:** owner/repo
**Generated:** 2026-02-11 10:30:00 UTC
**PR Branch:** feature/branch-name

Note: Some Fix Instructions in this spec were refined based on user directives after initial review extraction.

## Summary
- **Total latest-cycle issues:** 5
- **Skipped by user decision:** 1
- **Major:** 1
- **Minor:** 3
- **Trivial:** 1

## User Decisions
- `skip` on issue `1`: On issue number one, don't fix.
- `override` on issue `3`: On issue number three, timeout should be 30 seconds.

## Issues to Address

### 1. `src/utils/helpers.ts`:45 - Major

**Problem:**
The function lacks proper error handling which could lead to uncaught exceptions...

**Fix Instructions:**
```
Add null-safe navigation and provide a default value fallback to prevent
potential runtime errors when data is undefined or null.
```

---

### 2. `src/components/Button.tsx`:12 - Minor

...

## Implementation Notes

- Prioritize Major issues before Minor/Trivial
- Validate each instruction against current code before applying changes
- Keep fixes scoped to finding intent

## Verification Checklist

After implementing fixes, verify:

- [ ] All latest-cycle unresolved findings reviewed
- [ ] Implemented fixes mapped back to each issue
- [ ] Tests/lint/type-check pass
- [ ] No new regressions introduced
```

## Workflow Integration

This skill is designed to integrate into a multi-step AI coding workflow:

### Typical Workflow

```
1. CodeRabbit reviews PR
         ↓
2. Generate spec (this skill)
   /review-spec 94
         ↓
3. Implement fixes
   [AI agent reads spec and fixes issues]
         ↓
4. Run code quality
   /code-quality
         ↓
5. Compose commits
   /compose-commits
         ↓
6. Verify implementation
   [AI agent checks spec verification checklist]
         ↓
7. Push and re-review
   [Optional: re-run CodeRabbit to confirm]
```

### Example Session

```
User: Generate a spec from PR #94 review comments

Claude: [Invokes /review-spec 94]
        ✅ Spec generated: specs/2026-02-21-061600-rouge-pr-94-issues-1.md
        Total latest-cycle issues: 5 (1 Major, 3 Minor, 1 Trivial)

User: Implement the fixes

Claude: [Reads specs/2026-02-21-061600-rouge-pr-94-issues-1.md]
        [Implements fixes one by one]
        [Runs tests after each fix]
        ✅ All 5 issues resolved

User: Run code quality and compose commits

Claude: [Runs /code-quality]
        [Runs /compose-commits]
        ✅ Ready to push
```

## Options and Arguments

### Required Arguments

- **`pr_number`** (int): GitHub pull request number

### Optional Flags

- **`--output-dir`** / **`-o`** (str): Output directory for spec file
  - Default: `specs` (in workspace root)
  - Example: `--output-dir docs/review-specs`

- **`--repo-path`** / **`-r`** (str): Repository path (overrides REPO_PATH env var)
  - Must be an absolute path
  - Example: `--repo-path /Users/username/projects/myrepo`

- **`--reviewer`** (str, repeatable): Reviewer login(s) to include
  - Default reviewers: `coderabbitai`, `coderabbitai[bot]`
  - Example: `--reviewer coderabbitai --reviewer coderabbitai[bot]`

- **`--rewrite`** (flag): Apply user directives to latest snapshot and regenerate spec
  - Example: `--rewrite`

- **`--decision`** (str, repeatable): Decision directive for rewrite mode
  - Example: `--decision "On issue number one, don't fix."`

- **`--decisions-file`** (str): Path to file containing directives (one per line) for rewrite mode
  - Example: `--decisions-file specs/pr-94-decisions.txt`

## How It Works

### 1. Fetch Review Cycles

- Reads PR reviews via `gh api repos/{owner}/{repo}/pulls/{pr}/reviews`.
- Filters by reviewer login (`coderabbitai`, `coderabbitai[bot]` by default).
- Orders cycles by `submitted_at`.

### 2. Source from Consolidated Prompt Blocks

- For each cycle, extracts only the section:
  - `🤖 Prompt for all review comments with AI agents`
- Parses findings from that block (file path, line range, instruction).

### 3. Build Fingerprints and Snapshots

- Creates stable finding fingerprints from normalized path/line/instruction.
- Persists per-cycle snapshots under:
  - `.rouge/review-spec/pr-{number}/snapshots/{review_id}.json`
- Maintains cycle index:
  - `.rouge/review-spec/pr-{number}/index.json`

### 4. Resolution Classification

- Uses review-thread evidence (`isResolved`) when a matching thread exists.
- Uses carry-forward across cycles for unmatched findings:
  - `resolved` (thread evidence)
  - `unresolved` (in latest cycle or persisted forward)
  - `likely_resolved` (disappears in later cycles)
  - `unknown` (insufficient evidence)

### 4a. Snapshot Rewrite Safety Mode

- Snapshots retain immutable originals:
  - `original_problem`, `original_fix_instructions`
- Rewrite mode applies user changes to effective fields:
  - `effective_problem`, `effective_fix_instructions`, `effective_status`
- Decision history is appended in snapshot `decisions[]`.

### 5. Generate Spec

- Uses latest-cycle unresolved/unknown findings as the action list.
- Adds cross-cycle resolution summary.

## Troubleshooting

### No Issues Found

**Symptom:**
```
✅ No findings extracted from consolidated prompt blocks.
```

**Possible causes:**
1. No reviews from configured reviewers on the PR
2. Review bodies do not include the consolidated prompt block
3. Prompt block exists but did not parse into findings

**Solutions:**
- Verify CodeRabbit has posted review cycles on the PR
- Check reviewer login filters (`--reviewer`)
- Inspect review body for `Prompt for all review comments with AI agents`

### Authentication Error

**Symptom:**
```
❌ Failed to fetch review cycles
   Check PR number and gh authentication.
```

**Solutions:**
```bash
# Check auth status
gh auth status

# Re-authenticate if needed
gh auth login

# Verify repo access
gh repo view
```

### Invalid PR Number

**Symptom:**
```
❌ Failed to fetch review cycles
```

**Solutions:**
- Verify PR number exists: `gh pr view <number>`
- Ensure you're in the correct repository
- Check GitHub API rate limits: `gh api rate_limit`

### Missing Dependencies

**Symptom:**
```
Command not found: gh
```

**Solutions:**
```bash
# Install GitHub CLI
brew install gh  # macOS
# See https://cli.github.com for other platforms

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Limitations

### Current Limitations

1. **Prompt dependence**: Findings are sourced from consolidated prompt blocks
   - If CodeRabbit changes this section format, parsing may miss items

2. **Author Filter**: Defaults to CodeRabbit reviewer accounts
   - Excludes human reviewer comments
   - Can be overridden with `--reviewer`

3. **Resolution confidence**: Not all findings map to thread IDs
   - Thread-matched items are highest confidence
   - Cycle carry-forward statuses are heuristic (`likely_resolved`)

4. **Single PR**: Processes one PR at a time
   - Batch processing not supported
   - Each PR requires separate invocation

### Known Issues

None currently. Please report issues to vault repository.

## Development

### Running Locally

```bash
# From vault repository
cd vault/skills/claude-code/global/review-spec

# Test with a PR
uv run scripts/review_spec_cli.py <pr-number>

# With custom output
uv run scripts/review_spec_cli.py <pr-number> --output-dir /tmp/specs
```

### Code Quality

```bash
# Lint
uv run ruff check scripts/

# Format
uv run ruff format scripts/

# Type check
uv run mypy scripts/
```

### Testing Strategy

**Manual Testing:**
1. Test with PR containing unresolved CodeRabbit comments
2. Verify all issues extracted correctly
3. Confirm severity classification accurate
4. Validate markdown structure and formatting

**Edge Cases:**
- PR with no CodeRabbit review cycles
- PR with no comments from configured reviewers
- Reviews without the consolidated prompt block
- Invalid PR numbers
- Missing GitHub authentication

## See Also

- **Related Skills:**
  - `/spec` - General specification generation
  - `/compose-commits` - Commit composition after fixes
  - `/code-quality` - Code quality verification

- **Related Documentation:**
  - `SKILL.md` - Skill metadata and definition
  - Vault README - Overall vault documentation

- **External Resources:**
  - [GitHub CLI Documentation](https://cli.github.com/manual/)
  - [CodeRabbit Documentation](https://docs.coderabbit.ai/)
  - [PEP 723 - Inline Script Metadata](https://peps.python.org/pep-0723/)

## Contributing

This skill is part of the vault project. Contributions welcome:

1. Test with different PR scenarios
2. Report bugs or edge cases
3. Suggest enhancements (pagination, batch processing, etc.)
4. Improve documentation

## License

Part of the vault project. See vault LICENSE file.
