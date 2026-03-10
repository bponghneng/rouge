---
description: Read codebase context and build foundational knowledge
allowed_tools:
  - Read
  - Bash(ls -1 *)
  - Bash(ls | % Name)
---

# Prime Foundational Knowledge

Gather project context and return a concise summary.

## Instructions

- Read README.md and CLAUDE.md
- Run the following commands as **separate Bash tool calls** (do NOT chain with `&&`):
  - `ls -1` (\*nix shell) or `ls | % Name` (PowerShell)
  - `git -C <repo-dir> ls-files` (use `-C` to target the repo dir; never use `cd ... &&`; do NOT pipe to head)
- Constraints:
  - Minimize reading source code files
  - Minimize searching for patterns across the codebase
  - Minimize analysis of code relationships or architecture
  - Use directory structure and config files to infer organization
  - Keep the summary concise and actionable
  - Focus on information needed to start working effectively
- Output a **concise structured summary** under 200 words covering:
  - Project overview
  - Technology stack
  - Code organization
  - Development context, including coding and workflow conventions
