from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def normalize_repo_name(repo: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", repo.strip().lower()).strip("-")
    return normalized or "repo"


def next_cycle_sequence_number(
    output_dir: Path, repo: str, pr_number: int, cycle_id: int
) -> int:
    repo_name = normalize_repo_name(repo)
    pattern = re.compile(
        rf"^\d{{4}}-\d{{2}}-\d{{2}}-\d{{6}}-{re.escape(repo_name)}-pr-{pr_number}"
        rf"-c{cycle_id}-issues-(\d+)\.md$"
    )
    max_sequence = 0
    if output_dir.exists():
        for file in output_dir.glob("*.md"):
            match = pattern.match(file.name)
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))
    return max_sequence + 1


def next_merged_sequence_number(output_dir: Path, repo: str, pr_number: int) -> int:
    repo_name = normalize_repo_name(repo)
    pattern = re.compile(
        rf"^\d{{4}}-\d{{2}}-\d{{2}}-\d{{6}}-{re.escape(repo_name)}-pr-{pr_number}"
        rf"-merged-issues-(\d+)\.md$"
    )
    max_sequence = 0
    if output_dir.exists():
        for file in output_dir.glob("*.md"):
            match = pattern.match(file.name)
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))
    return max_sequence + 1


def next_sequence_number(output_dir: Path, repo: str, pr_number: int) -> int:
    """Kept for backward compatibility."""
    return next_merged_sequence_number(output_dir, repo, pr_number)


def build_cycle_spec_filename(
    timestamp: datetime, repo: str, pr_number: int, cycle_id: int, sequence: int
) -> str:
    ts = timestamp.strftime("%Y-%m-%d-%H%M%S")
    repo_name = normalize_repo_name(repo)
    return f"{ts}-{repo_name}-pr-{pr_number}-c{cycle_id}-issues-{sequence}.md"


def build_merged_spec_filename(
    timestamp: datetime, repo: str, pr_number: int, sequence: int
) -> str:
    ts = timestamp.strftime("%Y-%m-%d-%H%M%S")
    repo_name = normalize_repo_name(repo)
    return f"{ts}-{repo_name}-pr-{pr_number}-merged-issues-{sequence}.md"


def build_spec_filename(
    timestamp: datetime, repo: str, pr_number: int, sequence: int
) -> str:
    """Kept for backward compatibility."""
    return build_merged_spec_filename(timestamp, repo, pr_number, sequence)


def render_spec(
    pr_number: int,
    issues: List[Dict[str, Any]],
    skipped_issues: List[Dict[str, Any]],
    applied_decisions: List[Dict[str, Any]],
    owner: str,
    repo: str,
    all_findings: List[Dict[str, Any]],
    pr_branch: str,
    cycle_id: Optional[int] = None,
    commit_id: Optional[str] = None,
) -> str:
    counts = {"Major": 0, "Minor": 0, "Trivial": 0, "Unknown": 0}
    category_counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
        cat = issue.get("category", "")
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    status_counts = {
        "resolved": 0,
        "unresolved": 0,
        "likely_resolved": 0,
        "unknown": 0,
    }
    for finding in all_findings:
        status = finding.get("resolution_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    rewritten_count = sum(1 for issue in issues if issue.get("rewrite_applied"))

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    spec = f"# Code Review: Address PR #{pr_number} Review Issues\n\n"
    spec += f"**Repository:** {owner}/{repo}\n"
    spec += f"**Generated:** {timestamp}\n"
    spec += f"**PR Branch:** {pr_branch or 'N/A'}\n"
    if cycle_id is not None:
        commit_short = (commit_id or "")[:8] or "N/A"
        spec += f"**Review Cycle:** {cycle_id}\n"
        spec += f"**Commit:** {commit_short}\n"
    spec += "\n"

    if rewritten_count > 0:
        spec += (
            "Note: Some Fix Instructions in this spec were refined based on user "
            "directives after initial review extraction.\n\n"
        )

    category_summary = "".join(
        f"- **{cat}:** {category_counts[cat]}\n"
        for cat in ["Inline", "Outside diff", "Nitpick"]
        if cat in category_counts
    )

    spec += f"""## Summary

- **Total issues:** {len(issues)}
- **Skipped by user decision:** {len(skipped_issues)}
- **Major:** {counts["Major"]}
- **Minor:** {counts["Minor"]}
- **Trivial:** {counts["Trivial"]}
- **Unknown:** {counts["Unknown"]}
{category_summary}
## Resolution Analysis Across Cycles

- **Resolved (thread evidence):** {status_counts["resolved"]}
- **Unresolved:** {status_counts["unresolved"]}
- **Likely resolved (disappeared in later cycles):** {status_counts["likely_resolved"]}
- **Unknown:** {status_counts["unknown"]}

## User Decisions

"""

    if applied_decisions:
        for item in applied_decisions:
            action = item.get("action", item.get("status", "unknown"))
            index = item.get("issue_index", "?")
            reason = item.get("reason", "")
            suffix = f" ({reason})" if reason else ""
            spec += f"- `{action}` on issue `{index}`: {item['directive']}{suffix}\n"
    else:
        spec += "- No user decision directives applied.\n"

    spec += "\n## Issues to Address\n\n"

    severity_order = {"Major": 0, "Minor": 1, "Trivial": 2, "Unknown": 3}
    issues_sorted = sorted(
        issues,
        key=lambda x: (
            severity_order.get(x["severity"], 3),
            x.get("path") or "",
            x.get("start_line") or 0,
        ),
    )

    for i, issue in enumerate(issues_sorted, 1):
        loc = issue.get("line_range", "N/A")
        rendered_fix = issue.get(
            "effective_fix_instructions", issue.get("ai_prompt", "")
        )
        category = issue.get("category", "")
        category_line = f"**Category:** {category}\n" if category else ""
        sev = issue.get("severity", "Unknown")
        sev_label = f" - {sev}" if sev != "Unknown" else ""
        res_stat = issue.get("resolution_status", "")
        res_conf = issue.get("resolution_confidence", "")
        res_status = f"**Resolution Status (Confidence):** {res_stat} ({res_conf})"
        spec += f"""### {i}. `{issue["path"]}`:{loc}{sev_label}

{category_line}**Fix Instructions:**
`````
{rendered_fix}
`````

**Cycle:** review {issue["review_id"]} at {issue["submitted_at"]}
{res_status}
**Original Issue Number:** {issue.get("display_index", "?")}

---

"""

    if skipped_issues:
        spec += "## Skipped Issues\n\n"
        for issue in skipped_issues:
            loc = issue.get("line_range", "N/A")
            spec += (
                f"- `{issue.get('display_index', '?')}` `{issue['path']}`:"
                f"{loc} ({issue['severity']})\n"
            )
            if issue.get("user_note"):
                spec += f"  - Decision: {issue['user_note']}\n"
        spec += "\n"

    patch_title = f"PR #{pr_number} review issues"
    patch_cmd_parent = (
        f'rouge issue create --spec-file <SPEC_PATH> --title "{patch_title}" '
        "--type patch --parent-issue-id <PARENT_ISSUE_ID>"
    )
    spec += "## Create Rouge Patch Issue\n\n"
    if pr_branch:
        patch_cmd_branch = (
            f'rouge issue create --spec-file <SPEC_PATH> --title "{patch_title}" '
            f'--type patch --branch "{pr_branch}"'
        )
        spec += "- Branch-based command (from PR branch):\n"
        spec += f"```bash\n{patch_cmd_branch}\n```\n\n"
    spec += "- Parent-issue command:\n"
    spec += f"```bash\n{patch_cmd_parent}\n```\n\n"

    spec += """## Implementation Notes

- Prioritize Major issues before Minor/Trivial.
- Validate each instruction against current code before applying changes.
- Keep fixes scoped to the finding intent; avoid unrelated refactors.

## Verification Checklist

- [ ] All cycle unresolved findings reviewed
- [ ] Implemented fixes mapped back to each issue
- [ ] Tests/lint/type-check pass
- [ ] No new regressions introduced
"""

    return spec


def render_merged_spec(
    pr_number: int,
    cycle_sections: List[Dict[str, Any]],
    owner: str,
    repo: str,
    pr_branch: str,
) -> str:
    """Render a merged spec combining issues from multiple accepted cycles.

    Each entry in cycle_sections must have:
        cycle_id, submitted_at, commit_id,
        issues, skipped_issues, applied_decisions
    """
    total_issues = sum(len(s["issues"]) for s in cycle_sections)
    total_skipped = sum(len(s["skipped_issues"]) for s in cycle_sections)
    cycle_ids_str = ", ".join(str(s["cycle_id"]) for s in cycle_sections)

    counts: Dict[str, int] = {"Major": 0, "Minor": 0, "Trivial": 0, "Unknown": 0}
    for section in cycle_sections:
        for issue in section["issues"]:
            sev = issue.get("severity", "Unknown")
            counts[sev] = counts.get(sev, 0) + 1

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    spec = f"# Code Review: Address PR #{pr_number} Review Issues (Merged)\n\n"
    spec += f"**Repository:** {owner}/{repo}\n"
    spec += f"**Generated:** {timestamp}\n"
    spec += f"**PR Branch:** {pr_branch or 'N/A'}\n"
    spec += f"**Cycles Merged:** {cycle_ids_str}\n\n"

    spec += f"""## Summary

- **Total issues:** {total_issues}
- **Skipped by user decision:** {total_skipped}
- **Cycles:** {len(cycle_sections)}
- **Major:** {counts["Major"]}
- **Minor:** {counts["Minor"]}
- **Trivial:** {counts["Trivial"]}
- **Unknown:** {counts["Unknown"]}

"""

    severity_order = {"Major": 0, "Minor": 1, "Trivial": 2, "Unknown": 3}
    global_index = 1

    for section in cycle_sections:
        cycle_id = section["cycle_id"]
        submitted_at = section.get("submitted_at", "")
        commit_id = section.get("commit_id", "")
        commit_short = commit_id[:8] if commit_id else "N/A"
        issues = section["issues"]
        skipped = section["skipped_issues"]
        decisions = section["applied_decisions"]

        spec += (
            f"## Issues — Cycle {cycle_id} ({submitted_at}, commit: {commit_short})\n\n"
        )

        if decisions:
            spec += "**User Decisions:**\n"
            for item in decisions:
                action = item.get("action", item.get("status", "unknown"))
                idx = item.get("issue_index", "?")
                spec += f"- `{action}` on issue `{idx}`: {item['directive']}\n"
            spec += "\n"

        issues_sorted = sorted(
            issues,
            key=lambda x: (
                severity_order.get(x.get("severity", "Unknown"), 3),
                x.get("path") or "",
                x.get("start_line") or 0,
            ),
        )

        for issue in issues_sorted:
            loc = issue.get("line_range", "N/A")
            rendered_fix = issue.get(
                "effective_fix_instructions", issue.get("ai_prompt", "")
            )
            category = issue.get("category", "")
            category_line = f"**Category:** {category}\n" if category else ""
            sev = issue.get("severity", "Unknown")
            sev_label = f" - {sev}" if sev != "Unknown" else ""
            res_stat = issue.get("resolution_status", "")
            res_conf = issue.get("resolution_confidence", "")
            res_status = f"**Resolution Status (Confidence):** {res_stat} ({res_conf})"
            spec += f"""### {global_index}. `{issue["path"]}`:{loc}{sev_label}

{category_line}**Fix Instructions:**
`````
{rendered_fix}
`````

**Cycle:** review {issue["review_id"]} at {issue["submitted_at"]}
{res_status}

---

"""
            global_index += 1

        if skipped:
            spec += "**Skipped in this cycle:**\n"
            for issue in skipped:
                loc = issue.get("line_range", "N/A")
                sev = issue.get("severity", "Unknown")
                spec += f"- `{issue['path']}`:{loc} ({sev})"
                if issue.get("user_note"):
                    spec += f" — {issue['user_note']}"
                spec += "\n"
            spec += "\n"

    patch_title = f"PR #{pr_number} review issues"
    spec += "## Create Rouge Patch Issue\n\n"
    if pr_branch:
        patch_cmd_branch = (
            f'rouge issue create --spec-file <SPEC_PATH> --title "{patch_title}" '
            f'--type patch --branch "{pr_branch}"'
        )
        spec += "- Branch-based command (from PR branch):\n"
        spec += f"```bash\n{patch_cmd_branch}\n```\n\n"
    patch_cmd_parent = (
        f'rouge issue create --spec-file <SPEC_PATH> --title "{patch_title}" '
        "--type patch --parent-issue-id <PARENT_ISSUE_ID>"
    )
    spec += "- Parent-issue command:\n"
    spec += f"```bash\n{patch_cmd_parent}\n```\n\n"

    spec += """## Implementation Notes

- Prioritize Major issues before Minor/Trivial.
- Address each cycle's issues in order; earlier cycles may provide context for
  later ones.
- Validate each instruction against current code before applying changes.
- Keep fixes scoped to the finding intent; avoid unrelated refactors.

## Verification Checklist

- [ ] All cycle issues reviewed and implemented
- [ ] Implemented fixes mapped back to each issue
- [ ] Tests/lint/type-check pass
- [ ] No new regressions introduced
"""

    return spec


def write_spec_file(
    spec_content: str,
    output_base: Path,
    working_dir: Path,
    repo: str,
    pr_number: int,
    cycle_id: Optional[int] = None,
) -> Tuple[Path, str]:
    timestamp = datetime.now(tz=timezone.utc)
    if cycle_id is not None:
        sequence = next_cycle_sequence_number(output_base, repo, pr_number, cycle_id)
        filename = build_cycle_spec_filename(
            timestamp, repo, pr_number, cycle_id, sequence
        )
    else:
        sequence = next_merged_sequence_number(output_base, repo, pr_number)
        filename = build_merged_spec_filename(timestamp, repo, pr_number, sequence)

    spec_output_path = output_base / filename
    spec_output_path.parent.mkdir(parents=True, exist_ok=True)
    spec_output_path.write_text(spec_content)

    try:
        display_path = str(spec_output_path.relative_to(working_dir))
    except ValueError:
        display_path = str(spec_output_path)

    return spec_output_path, display_path
