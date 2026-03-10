---
description: Generate a workspace-specific README.md from an embedded workspace template
---

# Generate Workspace README

Examine the current workspace and produce a completed workspace `README.md` by replacing all placeholders in the embedded template below with workspace-specific details.

## Instructions

1. Read:
   - Existing `README.md` (if present)
   - Existing `AGENTS.md` (if present)
2. Inspect workspace and repository context with lightweight commands:
   - Identify all top-level repositories in the workspace by checking each top-level directory for a `.git` directory (for example: `find . -maxdepth 2 -type d -name .git`).
   - `ls -1`
   - `git ls-files | head -100` (run from each relevant repo root as needed)
   - Treat directories containing `.git` as repositories and use that set to determine the primary project repo referenced in the generated workspace `README.md`.
3. Infer details primarily from directory structure and config/docs. Minimize deep source-code analysis.
4. Replace every placeholder token in the template, including all `<...>` entries such as:
   - project name
   - repo directory
   - repo description
   - relevant key files/directories
   - source directory focus
5. Preserve the template's overall structure and intent; only customize workspace-specific content.
6. If a detail is genuinely unknown, use a concrete fallback like `Not specified in this workspace` instead of leaving placeholders.
7. Write the completed result to `README.md` in the current workspace root.

## Embedded Template

```markdown
# <Project Name> Workspace

This directory is a **workspace folder** containing AI coding agent configuration and automation resources.

## Important

**This is NOT the project repository.** The actual project code and files are located in:


`<repo directory>/` - [Description of repo]


## Relevant Files

Focus on the following files:
- `ai_docs/` - Contains scraped web resources for AI coding agent context.
- `specs/` - Contains technical specs and planning documents.
- `<repo directory>/<key-file1>` - [description of key file1]
- `<repo directory>/README.md` - [description of README.md]
- `<repo directory>/<source directory>/**` - [description of source directory]

## Irrelevant Files

The following files and directories are not relevant to the project. They support the AI coding agent workflows.

- **Agent Configuration** - Instructions and context for AI coding agents
  - [AGENTS.md](AGENTS.md)
  - [CLAUDE.md](CLAUDE.md)
  - [WARP.md](WARP.md)
- **AI Coding Agent Customizations** - Slash commands, subagent definitions, modes, rules and workflows
  - [.claude/commands/](.claude/commands/) - Claude Code slash commands
  - [.claude/skills/](.claude/skills/) - Claude Code skills
  - [.claude/subagents/](.claude/subagents/) - Claude Code subagents
  - [.codex/prompts/](.codex/prompts/) - Codex CLI slash commands
  - [.codex/skills/](.codex/skills/) - Codex CLI skills
- **Automation and Logging** - Scripts and logs for orchestrating AI coding agent workflows
  - [.rouge](.rouge/) - Rouge agent orchestration outputs
```
