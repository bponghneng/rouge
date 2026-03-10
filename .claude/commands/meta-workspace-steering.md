---
description: Generate a workspace-specific AGENTS.md from an embedded template
---

# Generate AGENTS Steering File

Examine the current workspace and produce a completed `AGENTS.md` by replacing all placeholders in the embedded template below with workspace-specific details.

## Instructions

1. Read:
   - `README.md`
   - Existing `AGENTS.md` (if present)
2. Inspect workspace and repository context with lightweight commands:
   - Identify all top-level repositories in the workspace by checking each top-level directory for a `.git` directory (for example: `find . -maxdepth 2 -type d -name .git`).
   - `ls -1`
   - `git ls-files | head -100` (run from the actual project repo root if workspace root is not a git repo)
   - Treat directories containing `.git` as repositories and use that set to determine the primary project repo referenced in the generated `AGENTS.md`.
3. Infer details primarily from directory structure and config/docs. Minimize deep source-code analysis.
4. Replace every placeholder token in the template, including all `<...>` entries such as:
   - repo directory
   - project overview
   - package manager and setup
   - development commands
   - code quality tools
   - testing tools/strategy
   - key directories/files
   - key dependencies
5. Preserve the template's overall structure and intent; only customize workspace-specific content.
6. If a detail is genuinely unknown, use a concrete fallback like `Not specified in this workspace` instead of leaving placeholders.
7. Write the completed result to `AGENTS.md` in the current workspace root.

## Embedded Template

```markdown
# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

**⚠️ IMPORTANT: Workspace Structure**

This is a **workspace folder**. The project repository is `<repo directory>`. Read and follow `README.md` for complete details on relevant and irrelevant files.

## Project Overview

<description of project>

## Workflow Style & Collaboration Rules

### Code Changes & Investigation Workflow

- **Research First**: Investigate thoroughly before proposing solutions. Use search
  tools and documentation to gather facts rather than making assumptions.
- **Discuss Before Implementing**: Present findings and proposed approaches for
  approval before making code changes. Explain options and trade-offs.
- **Respect Original Code**: Try to understand where code came from and what problem
  it's solving before assuming it can be changed.
- **Question Assumptions**: If something doesn't work as expected, investigate the
  root cause. Look for version differences, environment issues, or missing context.

### Problem-Solving Workflow

1. **Analyze**: Read errors carefully and identify the real issue
2. **Research**: Use tools and documentation to understand the problem context
3. **Propose**: Present findings and suggest solution options with pros/cons
4. **Implement**: Only after approval, make minimal necessary changes
5. **Clean Up**: Remove temporary test files or debugging code

### Communication

- Ask clarifying questions when requirements are unclear
- Explain the "why" behind recommendations
- If blocked or uncertain, ask for guidance rather than guessing

## Simplicity-First Mindset

Your guidance is directed by these core principles:

1. **Start with MVP**: Focus on core functionality that delivers immediate value
2. **Avoid Premature Optimization**: Don't add features "just in case"
3. **Minimal Dependencies**: Only add what's absolutely necessary for requirements
4. **Clear Over Clever**: Simple, maintainable solutions over complex architectures

Apply these principles when evaluating whether complex patterns, or advanced optimizations are truly needed or if simpler solutions would suffice.

## Development Commands

**⚠️ IMPORTANT: Project Repository**: As noted in `Workspace Structure`, the project repository is `<repo directory>`. All of the development commands are run from the root of the project repository.

**Package Management**: <description of package manager>

**Development Server**:
- `<command1 to start development server>` - <Description of command1>
- `<command2 for another development task>` - <Description of command2>

**Code Quality Tools**:

- `<code-quality-tool1>`: <command to run1>
- `<code-quality-tool2>`: <command to run2>

**Testing**:
- `<test-tool1>`: <Description of test tool1>
- `<test-tool2>`: <Description of test tool2>

**<Other Tools, like Code Generators, Development Dependencies, etc.>**:
- `<other-tool1>`: <Description of other tool1>
- `<other-tool2>`: <Description of other tool2>

**Setup**: `<setup-command>` - <Description of setup command>

## Architecture

**⚠️ IMPORTANT: Project Architecture**: As noted in `Workspace Structure`, the project repository is in `<repo directory>/`.

**Current Structure**:

- `<key-directory1>` - <description of key directory1>
- `<key-directory2>` - <description of key directory2>
- `<key-file1>` - <description of key file1>
- `<key-file2>` - <description of key file2>

**Key Dependencies**:

- `<key-dependency-name1>` - <description of key dependency1>
- `<key-dependency-name2>` - <description of key dependency2>

## Testing Strategy

<description of testing strategy>

- <description of test type, e.g., unit tests, integration tests, and usage in codebase>
```

## Optional Focus

Use this optional input to bias the generated content toward a specific subproject or repo path when relevant:

`$ARGUMENTS`
