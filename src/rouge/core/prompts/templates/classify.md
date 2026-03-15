---
description: Classify a repository issue work item by type and complexity level.
model: sonnet
---

# Issue Classification

Based on the `Work Item` below, read the `Instructions` to classify the issue by type and complexity level using the `Issue Type Guidelines` and `Complexity Level Guidelines`. Respond with the exact `Output Format`.

**Important Reminder:** CLASSIFY ONLY! Do not research, plan, or implement. Just analyze the given work item and return JSON classification.

## Instructions

- CRITICAL: You are CLASSIFYING ONLY, not planning or implementing
- Analyze the work item details to determine both the issue type and complexity level
- Use the `Issue Type Guidelines` and `Complexity Level Guidelines` to make your determination
- Respond exclusively with JSON in the `Output Format` **with zero extra text**
- ABSOLUTELY NO prose, Markdown fences, explanations, or commentary—your entire reply must be a single JSON object
- Think carefully about both dimensions before finalizing your classification
- DO NOT launch research, planning, or implementation workflows
- DO NOT suggest solutions or create implementation plans
- ONLY classify based on the provided work item description

## Issue Type Guidelines

**Bug**: Issues that fix unintended behavior, errors, or broken functionality

- System crashes, errors, or exceptions
- Incorrect output or behavior vs. expected behavior
- Performance regressions or memory leaks
- Security vulnerabilities
- Broken user interface elements
- Data corruption or loss issues

**Feature**: Issues that add new functionality, capabilities, or user-facing features

- New user-facing features or capabilities
- New APIs or endpoints
- New integrations with external systems
- New data types or entities
- New user interface components
- New business logic or workflows

**Chore**: Issues related to maintenance, refactoring, tooling, or non-functional improvements

- Code refactoring or cleanup
- Dependency updates or migrations
- Documentation improvements
- Build system or CI/CD improvements
- Testing infrastructure enhancements
- Performance optimizations (non-regression)
- Code style or formatting changes

## Complexity Level Guidelines

**Simple**: 1-4 hours of work, low risk, well-understood requirements

- Single component or file changes
- Straightforward implementation with clear requirements
- Minimal testing requirements
- Low risk of breaking existing functionality
- No cross-team coordination needed
- Well-documented patterns or similar existing implementations

**Average**: 4-8 hours of work, moderate risk, some research required

- Multiple components or files involved
- Some research or investigation needed
- Moderate testing requirements
- Some risk of affecting existing functionality
- May require coordination with one other team member
- May need to establish new patterns or adapt existing ones

**Complex**: 8-24 hours of work, high risk, significant research and coordination

- Cross-system or architectural changes
- Significant research and investigation required
- Extensive testing and validation needed
- High risk of breaking existing functionality
- Requires coordination with multiple team members or stakeholders
- May involve new technologies or significant architectural decisions
- Requires careful planning and phased implementation

**Critical**: 24+ hours of work, very high risk, major architectural overhaul

- Complete system redesign or rearchitecture
- Multi-week or multi-sprint projects
- Requires extensive research, prototyping, and validation
- Critical business impact with high failure consequences
- Requires coordination across multiple teams or departments
- May involve new technology stacks or major platform changes
- Requires detailed project planning, risk assessment, and phased rollout
- Significant documentation and training requirements
- May require temporary workarounds or parallel systems

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "level": <simple|average|complex|critical>,
  "output": "classify",
  "type": <bug|chore|feature>
}

## Work Item

$ARGUMENTS
