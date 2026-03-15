---
description: ADW step: groups staged and unstaged git changes into logical units, creates conventional commits, and returns a JSON list of commits with messages, SHAs, and affected files.
model: sonnet
thinking: false
disable-model-invocation: true
---

# Compose Commits & PR Summary

Follow the `Instructions` and `Commit Process` to create conventional commits for the repositories described in `README.md`, then respond with the exact `Output Format`.

## Instructions

- Identify the repository or repositories to process, and process each in turn
- Use `cd` to change to the repo directory if needed
- Read current git status: `git status`
- Read current git diff (staged and unstaged changes): `git diff HEAD`
- Read current branch: `git branch --show-current`
- Read recent commits: `git log --oneline -10`
- Read `Conventional Commits Standard` to understand conventional commits

## Commit Process

### 1. Group Changes

Logically group related changes into commit units. Consider:

- Functional boundaries (each commit is a complete logical change)
- File relationships (related files usually go together)
- Change types (avoid mixing unrelated features, fixes, or chores)
- Include both staged and unstaged changes; re-stage files as needed to match logical commit groups

### 2. Compose Commit Messages

For each group, create a conventional commit message:

- Format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
- Keep the first line under 72 characters
- Use imperative mood ("Add" not "Added" or "Adds")
- Include body text for complex changes
- Add `BREAKING CHANGE:` footer if applicable

### 3. Execute Commits

For each group:

- Stage the relevant files using `git add`
- Commit with the composed message using `git commit -m`

### Edge Cases

- If changes span multiple unrelated features, create separate commits

## Conventional Commits Standard

<!-- Source: https://www.conventionalcommits.org/en/v1.0.0/#specification -->
The key words “MUST”, “MUST NOT”, “REQUIRED”, “SHALL”, “SHALL NOT”, “SHOULD”, “SHOULD NOT”, “RECOMMENDED”, “MAY”, and “OPTIONAL” in this document are to be interpreted as described in RFC 2119.

Commits MUST be prefixed with a type, which consists of a noun, feat, fix, etc., followed by the OPTIONAL scope, OPTIONAL !, and REQUIRED terminal colon and space.
The type feat MUST be used when a commit adds a new feature to your application or library.
The type fix MUST be used when a commit represents a bug fix for your application.
A scope MAY be provided after a type. A scope MUST consist of a noun describing a section of the codebase surrounded by parenthesis, e.g., fix(parser):
A description MUST immediately follow the colon and space after the type/scope prefix. The description is a short summary of the code changes, e.g., fix: array parsing issue when multiple spaces were contained in string.
A longer commit body MAY be provided after the short description, providing additional contextual information about the code changes. The body MUST begin one blank line after the description.
A commit body is free-form and MAY consist of any number of newline separated paragraphs.
One or more footers MAY be provided one blank line after the body. Each footer MUST consist of a word token, followed by either a :<space> or <space># separator, followed by a string value (this is inspired by the git trailer convention).
A footer’s token MUST use - in place of whitespace characters, e.g., Acked-by (this helps differentiate the footer section from a multi-paragraph body). An exception is made for BREAKING CHANGE, which MAY also be used as a token.
A footer’s value MAY contain spaces and newlines, and parsing MUST terminate when the next valid footer token/separator pair is observed.
Breaking changes MUST be indicated in the type/scope prefix of a commit, or as an entry in the footer.
If included as a footer, a breaking change MUST consist of the uppercase text BREAKING CHANGE, followed by a colon, space, and description, e.g., BREAKING CHANGE: environment variables now take precedence over config files.
If included in the type/scope prefix, breaking changes MUST be indicated by a ! immediately before the :. If ! is used, BREAKING CHANGE: MAY be omitted from the footer section, and the commit description SHALL be used to describe the breaking change.
Types other than feat and fix MAY be used in your commit messages, e.g., docs: update ref docs.
The units of information that make up Conventional Commits MUST NOT be treated as case-sensitive by implementors, with the exception of BREAKING CHANGE which MUST be uppercase.
BREAKING-CHANGE MUST be synonymous with BREAKING CHANGE, when used as a token in a footer.

## Output Format

Return ONLY valid JSON with zero additional text, formatting, markdown, or explanation.

{
  "output":"commits",
  "summary":"<concise summary of the commits>",
  "commits":[
    {
      "message":"<full conventional commit message>",
      "sha":"<commit SHA identifier>",
      "files":["repo/relative/path1","repo/relative/path2"]
    }
  ]
}
