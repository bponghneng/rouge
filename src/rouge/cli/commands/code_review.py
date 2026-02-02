"""CLI command for code review workflow."""

import os
import subprocess

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.core.workflow.shared import get_repo_path

app = typer.Typer(help="Code review workflow commands")


def resolve_to_sha(ref: str) -> str:
    """Resolve a git reference to a full SHA.

    Runs ``git rev-parse <ref>`` to validate the reference and return the
    resolved commit SHA.

    Args:
        ref: A git reference such as a branch name, tag, or commit SHA.

    Returns:
        The full SHA string for the resolved reference.

    Raises:
        typer.Exit: If the reference cannot be resolved.
    """
    repo_path = get_repo_path()
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: Invalid git reference '{ref}' (from {repo_path})", err=True)
        typer.echo(f"stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo("Error: git is not installed or not in PATH", err=True)
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def run_code_review(
    base_commit: str = typer.Option(
        ...,
        "--base-commit",
        help="Git reference (branch, tag, or SHA) to compare against",
        show_default=False,
    ),
) -> None:
    """Run a code review workflow against a base commit.

    Resolves the provided git reference to a SHA, then executes the
    code-review workflow pipeline.

    Example:
        rouge code-review --base-commit main
        rouge code-review --base-commit abc1234
    """
    # Validate git repository exists
    repo_path = get_repo_path()
    git_dir = os.path.join(repo_path, ".git")
    if not os.path.exists(git_dir):
        typer.echo(
            f"Error: No git repository found at {repo_path}\n"
            f"Set REPO_PATH environment variable or run from the repository directory",
            err=True,
        )
        raise typer.Exit(1)

    # Resolve the git reference to a full SHA
    base_sha = resolve_to_sha(base_commit)
    typer.echo(f"Resolved base commit: {base_sha}")

    try:
        success, workflow_id = execute_adw_workflow(
            issue_id=None,
            workflow_type="code-review",
            config={"base_commit": base_sha},
        )

        if success:
            typer.echo(f"Code review workflow {workflow_id} completed successfully")
        else:
            typer.echo(f"Code review workflow {workflow_id} failed", err=True)
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Error executing code review workflow: {exc}", err=True)
        raise typer.Exit(1)
