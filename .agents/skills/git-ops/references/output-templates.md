# Output Templates

Use human-readable Markdown. Do not return JSON.

## Compose Commits Output

```markdown
## Commits Created

- <sha1> <commit message 1>
- <sha2> <commit message 2>
- ...
```

## Pull Request / Merge Request Output

```markdown
## Pull/Merge Request

### Title
<title>

### Summary
<markdown summary body>

### Commits
- <sha1> <commit message 1>
- <sha2> <commit message 2>
- ...

### URL
<pr-or-mr-url-or-note-if-not-created>
```
