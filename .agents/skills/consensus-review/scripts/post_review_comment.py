#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "click>=8.0.0",
# ]
# ///

"""
Post Consensus Review Comment

This script:
1. Reads DEV_SEC_OPS_PLATFORM from .env at the workspace root
2. Reads synthesizer output from a temp file
3. Determines if the review is clean
4. Reads pre-generated bullet summary from --summary-file (required when review has issues)
5. Posts the comment to GitHub (gh) or GitLab (glab)
"""

import shutil
import subprocess
import sys
from pathlib import Path

import click

# Resolve absolute paths for external tools at module load (prevents PATH hijacking)
GH = shutil.which("gh")
GLAB = shutil.which("glab")


def read_platform_from_env() -> str:
    """Read DEV_SEC_OPS_PLATFORM from .env file at the workspace root."""
    env_path = Path(".env")
    if not env_path.exists():
        return "github"

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DEV_SEC_OPS_PLATFORM="):
                raw = line[len("DEV_SEC_OPS_PLATFORM=") :]
                value = raw.strip().strip('"').strip("'")
                return value.lower()

    return "github"


def check_if_clean(text: str) -> bool:
    """Determine if the review is clean (no actionable issues found).

    Heuristic: generous interpretation — if any issue markers are present,
    treat as having issues. If unsure, treat as has issues.
    """
    issue_markers = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "nitpick"]
    text_lower = text.lower()
    for marker in issue_markers:
        if marker.lower() in text_lower:
            return False

    # Also check for score indicators suggesting problems (e.g. "score: 3/10")
    import re

    score_pattern = re.compile(r"score[:\s]+(\d+)\s*/\s*10", re.IGNORECASE)
    for match in score_pattern.finditer(text):
        score = int(match.group(1))
        if score < 8:
            return False

    return True


def build_summary_lines(summary_file: str) -> list[str]:
    """Read pre-generated bullet summary lines from a file."""
    content = Path(summary_file).read_text(encoding="utf-8").strip()
    return [line for line in content.splitlines() if line.strip()]


def build_comment_body(
    synthesizer_output: str, *, is_clean: bool, summary_file: str | None = None
) -> str:
    """Build the full comment body."""
    full_output_block = (
        "<details>\n"
        "<summary>Full review output</summary>\n\n"
        f"{synthesizer_output}\n\n"
        "</details>"
    )

    if is_clean:
        return (
            "## \u2705 Consensus Review\n\n"
            "No issues found. The review passed with no actionable findings.\n\n"
            f"{full_output_block}"
        )
    else:
        bullet_lines = build_summary_lines(summary_file) if summary_file else []
        summary_text = "\n".join(bullet_lines)
        return (
            "## \u26a0\ufe0f Consensus Review\n\n"
            "### Summary\n"
            f"{summary_text}\n\n"
            f"{full_output_block}"
        )


def post_comment_github(pr_number: int, body: str, repo_dir: str = ".") -> None:
    """Post a comment to a GitHub PR."""
    if not GH:
        raise FileNotFoundError("gh executable not found in PATH")
    subprocess.run(
        [GH, "pr", "comment", str(pr_number), "--body", body],
        cwd=repo_dir,
        check=True,
    )


def post_comment_gitlab(pr_number: int, body: str, repo_dir: str = ".") -> None:
    """Post a note to a GitLab MR."""
    if not GLAB:
        raise FileNotFoundError("glab executable not found in PATH")
    subprocess.run(
        [GLAB, "mr", "note", str(pr_number), "--message", body],
        cwd=repo_dir,
        check=True,
    )


@click.command()
@click.option("--pr-number", required=True, type=int, help="PR/MR number to comment on")
@click.option(
    "--review-file",
    required=True,
    type=click.Path(exists=True, readable=True),
    help="Path to temp file containing the full synthesizer output text",
)
@click.option(
    "--repo-dir",
    default=".",
    show_default=True,
    help="Path to the git repo directory where gh/glab commands should run",
)
@click.option(
    "--summary-file",
    default=None,
    type=click.Path(exists=True, readable=True),
    help="Path to file containing pre-generated bullet summary lines (skips claude -p call)",
)
def main(pr_number: int, review_file: str, repo_dir: str, summary_file: str | None) -> None:
    """Post a consensus review comment to a GitHub PR or GitLab MR."""

    # 1. Read platform from .env
    platform = read_platform_from_env()

    # 2. Read synthesizer output from file
    review_path = Path(review_file)
    try:
        synthesizer_output = review_path.read_text(encoding="utf-8")
    except OSError as e:
        click.echo(f"Error: Failed to read review file '{review_file}': {e}", err=True)
        sys.exit(1)

    if not synthesizer_output.strip():
        click.echo("Error: Review file is empty.", err=True)
        sys.exit(1)

    # 3. Determine if review is clean
    is_clean = check_if_clean(synthesizer_output)

    # 4. Build comment body (uses pre-generated summary from --summary-file when provided)
    comment_body = build_comment_body(synthesizer_output, is_clean=is_clean, summary_file=summary_file)

    # 5. Post the comment
    try:
        if platform == "gitlab":
            post_comment_gitlab(pr_number, comment_body, repo_dir=repo_dir)
        else:
            # Default to github for any other value
            post_comment_github(pr_number, comment_body, repo_dir=repo_dir)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(
            f"Error: Failed to post comment (exit code {e.returncode}): {e}", err=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
