#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "click>=8.0.0",
#   "python-dotenv>=1.0.0",
# ]
# ///

"""
Consensus Review Context Recovery

Scans the audit trail directory for a given PR/MR number and outputs a
structured context block to stdout. The calling agent uses this output to
determine the next cycle number, locate the plan file, load prior cycle
summaries, and pass operator-accepted findings to the synthesizer.

Platform detection:
  Reads DEV_SEC_OPS_PLATFORM from .env at the working directory root.
  "github" (default) → audit dir prefix "pr-"
  "gitlab"           → audit dir prefix "mr-"
  Override with --platform if .env is absent or you need to force a value.

Exit codes:
  0 — context block written to stdout
  1 — usage error
"""

import re
import sys
from pathlib import Path

import click
from dotenv import dotenv_values

_SCORE_RE = re.compile(r"Quality Score.*?(\d+)/100", re.IGNORECASE)

_DIR_PREFIX = {
    "github": "pr",
    "gitlab": "mr",
}


def _read_platform(override: str | None) -> str:
    """Return the normalised platform name from --platform override or .env."""
    if override:
        return override.strip().lower()
    env = dotenv_values(".env")
    raw = env.get("DEV_SEC_OPS_PLATFORM", "github")
    return raw.strip().strip('"').strip("'").lower()


def _dir_prefix(platform: str) -> str:
    """Return 'pr' for GitHub, 'mr' for GitLab, defaulting to 'pr'."""
    return _DIR_PREFIX.get(platform, "pr")


def _extract_score(review_file: Path) -> str:
    """Return 'NN/100' from a review file, or '?/100' if not found."""
    try:
        text = review_file.read_text(encoding="utf-8")
    except OSError:
        return "?/100"
    match = _SCORE_RE.search(text)
    return f"{match.group(1)}/100" if match else "?/100"


def _read_file_or_note(path: Path, label: str) -> str:
    """Return file contents, or an italicised note if the file is missing."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return f"*{label} not found at {path}*"


@click.command()
@click.argument("mr_number", type=int, metavar="NUMBER")
@click.option(
    "--platform",
    default=None,
    show_default=False,
    help=(
        "Override platform detection. Accepted values: github, gitlab. "
        "Defaults to DEV_SEC_OPS_PLATFORM in .env, or 'github' if absent."
    ),
)
@click.option(
    "--reviews-dir",
    default=".rouge/reviews",
    show_default=True,
    help="Root directory that contains per-PR/MR audit trail sub-directories.",
)
def main(mr_number: int, platform: str | None, reviews_dir: str) -> None:
    """Output a structured prior-cycle context block for a given PR/MR number."""

    resolved_platform = _read_platform(platform)
    prefix = _dir_prefix(resolved_platform)
    platform_label = "MR" if resolved_platform == "gitlab" else "PR"

    log_dir = Path(reviews_dir) / f"{prefix}-{mr_number}"

    # ------------------------------------------------------------------ #
    # First cycle — no prior context exists                               #
    # ------------------------------------------------------------------ #
    if not log_dir.exists():
        click.echo(
            f"## Consensus Review — Prior Cycle Context for "
            f"{platform_label} {mr_number}\n\n"
            f"**Platform:** {resolved_platform}\n"
            f"**Log directory:** `{log_dir}` — does not exist yet (first cycle)\n"
            f"**Next cycle:** 01\n\n"
            "No prior cycle history. A plan file may be provided separately.\n"
        )
        return

    # ------------------------------------------------------------------ #
    # Determine next cycle from existing review files                     #
    # ------------------------------------------------------------------ #
    review_files = sorted(log_dir.glob("review-*.md"))
    cycle = len(review_files) + 1
    cycle_label = f"{cycle:02d}"

    # ------------------------------------------------------------------ #
    # Plan file                                                           #
    # ------------------------------------------------------------------ #
    plan_file = log_dir / "plan.md"
    plan_status = (
        f"`{plan_file}` ✓ present"
        if plan_file.exists()
        else f"`{plan_file}` ✗ missing"
    )

    # ------------------------------------------------------------------ #
    # Build prior-cycle table                                             #
    # ------------------------------------------------------------------ #
    fix_files = {f.stem for f in log_dir.glob("fix-*.md")}
    summary_files = sorted(log_dir.glob("summary-*.md"))

    prior_rows: list[str] = []
    for i, rf in enumerate(review_files, start=1):
        c = f"{i:02d}"
        score = _extract_score(rf)
        fix_label = f"`fix-{c}.md` ✓" if f"fix-{c}" in fix_files else "absent"
        prior_rows.append(f"| {c} | {score} | {fix_label} |")

    table_lines = [
        "| Cycle | Score  | Fix log |",
        "|-------|--------|---------|",
        *prior_rows,
    ]

    # ------------------------------------------------------------------ #
    # Inline cycle summaries (concise — from summary-*.md)               #
    # ------------------------------------------------------------------ #
    summary_sections: list[str] = []
    for i, sf in enumerate(summary_files, start=1):
        c = f"{i:02d}"
        score = _extract_score(review_files[i - 1]) if i <= len(review_files) else "?/100"
        content = _read_file_or_note(sf, f"summary-{c}.md")
        summary_sections.append(f"**Cycle {c} ({score}):**\n{content}")

    # ------------------------------------------------------------------ #
    # Operator-accepted findings                                          #
    # ------------------------------------------------------------------ #
    accepted_files = sorted(log_dir.glob("accepted-*.md"))
    accepted_sections: list[str] = []
    for af in accepted_files:
        content = _read_file_or_note(af, af.name)
        accepted_sections.append(f"**From `{af.name}`:**\n{content}")

    # ------------------------------------------------------------------ #
    # Assemble output                                                     #
    # ------------------------------------------------------------------ #
    lines: list[str] = [
        f"## Consensus Review — Prior Cycle Context for {platform_label} {mr_number}",
        "",
        f"**Platform:** {resolved_platform}",
        f"**Log directory:** `{log_dir}`",
        f"**Plan file:** {plan_status}",
        f"**Next cycle:** {cycle_label}",
        "",
    ]

    if prior_rows:
        lines += ["### Prior Cycles", ""] + table_lines + [""]

    if summary_sections:
        lines += ["### Cycle Summaries", ""] + [
            s + "\n" for s in summary_sections
        ]

    if accepted_sections:
        lines += [
            "### Operator-Accepted Findings",
            "",
            "> These findings were explicitly accepted by the operator in a prior cycle.",
            "> The synthesizer **must not re-raise** them as new findings.",
            "",
        ] + [s + "\n" for s in accepted_sections]
    else:
        lines += ["### Operator-Accepted Findings", "", "None.", ""]

    click.echo("\n".join(lines))


if __name__ == "__main__":
    main()
