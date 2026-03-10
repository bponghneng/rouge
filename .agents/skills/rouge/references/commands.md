# Rouge CLI Command Reference

## Issue management

- Create issue:
  - `rouge issue create "Fix authentication bug in login flow"`
  - `rouge issue create "Implement dark mode" --title "Dark mode feature"`
  - `rouge issue create --spec-file feature-spec.txt --title "New feature"`
  - `rouge issue create --spec-file patch-spec.txt --title "Bug fix" --type patch --branch my-branch`
  - `rouge issue create "Fix typo" --type patch --parent-issue-id 123`
- Read issue:
  - `rouge issue read 123`
- List issues:
  - `rouge issue list`
  - `rouge issue list --limit 10`
  - `rouge issue list --type patch --status pending`
  - `rouge issue list --format json --limit 20`
- Update issue:
  - `rouge issue update 123 --title "New Title"`
  - `rouge issue update 123 --assigned-to worker-id`
  - `rouge issue update 123 --description "Updated description"`
- Delete issue:
  - `rouge issue delete 123`
  - `rouge issue delete 123 --force`

## Workflow execution

- Run main workflow:
  - `rouge workflow run 123`
  - `rouge workflow run 123 --adw-id abc12345`
- Run patch workflow:
  - `rouge workflow patch 123`
  - `rouge workflow patch 123 --adw-id abc12345`
- Run code review workflow:
  - `rouge workflow codereview 123`
  - `rouge workflow codereview 123 --adw-id abc12345`

## Reset failed issue

- `rouge reset 123`
  - Resets a failed issue to pending, clears `assigned_to`
  - `main`/`codereview` issues: clears branch; `patch` issues: preserves branch

## Step operations

- List registered steps: `rouge step list`
- Run a single step:
  - `rouge step run fetch-issue --issue-id 123`
  - `rouge step run classify --issue-id 123 --adw-id abc12345`
  - `rouge step run patch-plan --issue-id 123 --workflow-type patch`
- Show dependency chain: `rouge step deps implement`
- Validate step registry: `rouge step validate`

## Artifact operations

- List artifacts: `rouge artifact list adw-xyz123`
- Show artifact: `rouge artifact show adw-xyz123 classification`
- Show artifact (raw): `rouge artifact show adw-xyz123 issue --raw`
- Delete artifact: `rouge artifact delete adw-xyz123 classification`
- List artifact types: `rouge artifact types`
- Show artifact path: `rouge artifact path adw-xyz123`

## Comment operations

- List comments: `rouge comment list`
- List by issue: `rouge comment list --issue-id 5`
- Filter comments: `rouge comment list --source agent --type plan --limit 5 --offset 10`
- Read comment: `rouge comment read 123`
- Read comment (JSON): `rouge comment read 123 --format json`

## Fast reference

- Discover commands: `rouge --help`
- Command help: `rouge <command> --help`
- Subcommand help: `rouge issue --help`, `rouge workflow --help`, `rouge step --help`, `rouge artifact --help`, `rouge comment --help`
