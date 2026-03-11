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
2. Reads synthesizer output from --review-file
3. Reads the pre-generated summary from --summary-file (required)
4. Builds the comment body using --is-clean to select the icon
5. Posts the comment to GitHub (gh) or GitLab (glab)

All intelligence (clean/not-clean determination, summary generation) lives in the
calling agent. This script is a formatter and poster only.
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


def build_summary_lines(summary_file: str) -> list[str]:
    """Read pre-generated bullet summary lines from a file."""
    content = Path(summary_file).read_text(encoding="utf-8").strip()
    return [line for line in content.splitlines() if line.strip()]


def build_comment_body(
    synthesizer_output: str, *, is_clean: bool, summary_file: str
) -> str:
    """Build the full comment body."""
    icon = "\u2705" if is_clean else "\u26a0\ufe0f"
    summary_lines = build_summary_lines(summary_file)
    summary_text = "\n".join(summary_lines)
    full_output_block = (
        "<details>\n"
        "<summary>Full review output</summary>\n\n"
        f"{synthesizer_output}\n\n"
        "</details>"
    )
    return (
        f"## {icon} Consensus Review\n\n"
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
    required=True,
    type=click.Path(exists=True, readable=True),
    help="Path to file containing pre-generated bullet summary lines (always required)",
)
@click.option(
    "--is-clean",
    is_flag=True,
    default=False,
    help="Pass this flag when the review is clean; selects the ✅ icon instead of ⚠️",
)
def main(
    pr_number: int, review_file: str, repo_dir: str, summary_file: str, is_clean: bool
) -> None:
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

    # 3. Build comment body
    comment_body = build_comment_body(
        synthesizer_output, is_clean=is_clean, summary_file=summary_file
    )

    # 4. Post the comment
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
