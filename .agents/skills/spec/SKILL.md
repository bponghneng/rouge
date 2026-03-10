---
description: "Interactive planning skill: build a concise outline iteratively, then save to a spec file and optionally create a rouge issue"
---
# Spec Planning Skill

## Overview

This skill runs a two-phase interactive planning workflow:

1. **Outline loop** — produce and refine a concise numbered outline on every turn
2. **Save phase** — triggered by the user; generate the full spec, save it, and offer to create a rouge issue

**CRITICAL**: You are PLANNING ONLY. Never implement code changes during this skill.

---

## Phase 1: Outline Loop

### On initial invocation (`/spec <text>`)

1. Read `@CLAUDE.md` and `@README.md` silently for project context. Carry forward only details relevant to the described work.
2. Classify the issue type: **Bug**, **Feature**, or **Chore** (see guidelines below).
3. Output a concise numbered outline — nothing else. Format:

```
[Bug | Feature | Chore]: <Short title>

1. <Scope item — one line>
2. <Scope item — one line>
3. ...
```

Keep each item to a single line. Aim for 3–8 items. No prose, no headers, no template.

### On every follow-up prompt (until save trigger)

- Incorporate the user's feedback into the outline.
- Re-output the full updated outline in the same format.
- Keep commentary minimal. Only add brief notes below the outline when there is something genuinely useful to flag: an ambiguity that could affect scope, a decision that needs the user's input, or a clarification that would materially improve the plan.

---

## Phase 2: Save Phase

### Trigger

Activate this phase when the user says something like:
- "save to a spec"
- "generate the spec"
- "finalize"
- or any clear intent to produce the final document

### Step 1: Generate the spec

Using the current outline as the source of truth, produce a single Markdown document using `@template.md`.

- **Title**: prefixed with issue type (e.g., "Bug: Fix login crash", "Feature: Add dark mode")
- **Intent**: one sentence
- **Value**: why this matters
- **Signals of success**: concise, observable outcomes
- **Implementation Plan**: scope items from the outline; include constraints, assumptions, and notes only if relevant
- **Length**: under 1,500 words

### Step 2: Save the file

Run `date +%Y-%m-%d-%H%M%S` to get the current timestamp, then save to `<workspace root>/specs/<timestamp>-<slug>.md`.

Generate `<slug>` from the full spec title by: lowercasing; replacing spaces and punctuation runs with single hyphens; removing characters except `a-z`, `0-9`, `-`; collapsing repeated hyphens; trimming leading/trailing hyphens; truncating to ~50 characters at a word boundary.

### Step 3: Prompt for rouge issue creation

After saving, ask the user:

> Spec saved to `<path>`. Would you like to create a rouge issue from this spec?

Based on their response, run one of:

- **Yes / confirm (default)**: `uv run rouge issue create --spec-file <path> --title "<spec title>"`
- **"code review issue"**: `uv run rouge issue create --spec-file <path> --title "<spec title>" --type codereview`
- **"patch issue"**: `uv run rouge issue create --spec-file <path> --title "<spec title>" --type patch`
- **No / decline**: acknowledge and stop

---

## Issue Type Guidelines

**Bug**: Unintended behavior, errors, crashes, incorrect output, security vulnerabilities, data issues.

**Feature**: New user-facing functionality, APIs, integrations, UI components, business logic.

**Chore**: Refactoring, dependency updates, documentation, build/CI improvements, code style, non-regression performance work.

---

## Initial Issue Description

$ARGUMENTS
