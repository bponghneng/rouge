"""Create GitHub pull request step implementation."""

import logging
import os
import re
import shutil
import subprocess
from typing import ClassVar

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ArtifactType,
    GhPullRequestArtifact,
    PullRequestArtifactBase,
)
from rouge.core.workflow.pull_request_step_base import PullRequestStepBase
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.step_utils import _emit_and_log
from rouge.core.workflow.types import StepResult

_logger = get_logger(__name__)


def _post_gh_attachment_comment(
    repo_path: str,
    pr_number: int,
    body: str,
    env: dict[str, str],
) -> None:
    """Post or update the Rouge review-context comment on a GitHub PR."""
    marker = "<!-- rouge-review-context -->"
    tagged_body = f"{marker}\n{body}"

    # List existing comments and find one with our marker
    list_cmd = [
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--json",
        "comments",
        "--jq",
        '.comments[] | select(.body | startswith("<!-- rouge-review-context -->")) | .databaseId',
    ]
    result = subprocess.run(
        list_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
    )

    existing_comment_id = (
        result.stdout.strip().split("\n")[0]
        if result.returncode == 0 and result.stdout.strip()
        else None
    )

    if existing_comment_id and existing_comment_id.isdigit():
        update_cmd = [
            "gh",
            "api",
            "--method",
            "PATCH",
            f"/repos/{{owner}}/{{repo}}/issues/comments/{existing_comment_id}",
            "-f",
            f"body={tagged_body}",
        ]
        update_result = subprocess.run(
            update_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if update_result.returncode != 0:
            _logger.warning(
                "Failed to update review-context comment on PR #%d: %s",
                pr_number,
                update_result.stderr,
            )
        else:
            _logger.info("Updated review-context comment on PR #%d", pr_number)
    else:
        cmd = ["gh", "pr", "comment", str(pr_number), "--body", tagged_body]
        create_result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if create_result.returncode != 0:
            _logger.warning(
                "Failed to post review-context comment on PR #%d: %s",
                pr_number,
                create_result.stderr,
            )
        else:
            _logger.info("Posted review-context comment on PR #%d", pr_number)


class GhPullRequestStep(PullRequestStepBase):
    """Create GitHub pull request via gh CLI."""

    cli_binary: ClassVar[str] = "gh"
    pat_env_var: ClassVar[str] = "GITHUB_PAT"
    token_env_key: ClassVar[str] = "GH_TOKEN"
    artifact_slug: ClassVar[ArtifactType] = "gh-pull-request"
    platform: ClassVar[str] = "github"
    entity_name: ClassVar[str] = "PR"
    entity_prefix: ClassVar[str] = "#"
    output_key_prefix: ClassVar[str] = "pull-request"

    @property
    def name(self) -> str:
        return "Creating GitHub pull request"

    @property
    def artifact_class(self) -> type[PullRequestArtifactBase]:
        return GhPullRequestArtifact

    def _check_cli_available(
        self, context: WorkflowContext, logger: logging.Logger
    ) -> StepResult | None:
        if not shutil.which("gh"):
            skip_msg = "PR creation skipped: gh CLI not found in PATH"
            logger.info(skip_msg)
            logger.debug("Current PATH: %s", os.environ.get("PATH", ""))
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)
        return None

    def _list_cmd_args(self, branch_name: str) -> list[str]:
        return ["gh", "pr", "list", "--head", branch_name, "--json", "url,number"]

    def _parse_existing_item(self, item: dict) -> tuple[str, int | None]:
        return (item.get("url", ""), item.get("number"))

    def _create_cmd_args(self, title: str, summary: str, draft: bool) -> list[str]:
        cmd = ["gh", "pr", "create", "--title", title, "--body", summary]
        if draft:
            cmd.append("--draft")
        return cmd

    def _parse_create_output(self, stdout: str) -> tuple[str, int | None] | None:
        url = stdout.strip()
        if not url:
            return None
        number: int | None = None
        match = re.search(r".*/pull/(\d+)", url)
        if match:
            number = int(match.group(1))
        return (url, number)

    def _post_attachment(self, repo_path: str, number: int, body: str, env: dict[str, str]) -> None:
        _post_gh_attachment_comment(repo_path, number, body, env)

        if result.returncode != 0:
            error_msg = (
                f"gh pr create failed for {repo_name} "
                f"(exit code {result.returncode}): {result.stderr}"
            )
            logger.warning(
                "gh pr create failed for %s (exit code %d): %s",
                repo_name,
                result.returncode,
                result.stderr,
            )
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pull-request-failed", "error": error_msg},
            )
            # Continue to next repo; partial progress is already saved
            return

        # Parse PR URL from output (gh pr create outputs the URL)
        pr_url = result.stdout.strip()
        logger.info("Pull request created for %s: %s", repo_name, pr_url)

        # Extract PR number from URL
        pr_number = None
        number_match = re.search(r".*/pull/(\d+)", pr_url)
        if number_match:
            pr_number = int(number_match.group(1))

        entry = PullRequestEntry(
            repo=repo_name,
            repo_path=repo_path,
            url=pr_url,
            number=pr_number,
            adopted=False,
        )
        pull_requests.append(entry)

        # Write artifact after each repo so partial progress survives failures
        artifact = GhPullRequestArtifact(
            workflow_id=context.adw_id,
            pull_requests=pull_requests,
            platform="github",
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved gh-pull-request artifact after creating PR for %s", repo_name)

        if attachment_md and entry.number:
            try:
                _post_gh_attachment_comment(
                    repo_path=repo_path,
                    pr_number=entry.number,
                    body=attachment_md,
                    env=env,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "Failed to post attachment comment on PR #%d: %s",
                    entry.number,
                    exc,
                )

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitHub pull request using gh CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Try to load pr_details from artifact if not in context (optional)
        pr_details = context.load_optional_artifact(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: {"title": a.title, "summary": a.summary, "commits": a.commits},
        )

        attachment_md = load_and_render_attachment(context)

        if result := self._check_preconditions(context, pr_details, logger):
            return result

        # pr_details is guaranteed non-None after preconditions pass
        assert pr_details is not None
        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        github_pat = os.environ.get("GITHUB_PAT", "")

        try:
            # Execute with GH_TOKEN environment variable
            env = os.environ.copy()
            env["GH_TOKEN"] = github_pat

            # Seed pull_requests from existing artifact for rerun continuity (Layer 0)
            pull_requests: list[PullRequestEntry] = []
            if context.artifact_store.artifact_exists("gh-pull-request"):
                try:
                    existing_artifact = context.artifact_store.read_artifact(
                        "gh-pull-request", GhPullRequestArtifact
                    )
                    pull_requests = list(existing_artifact.pull_requests)
                    logger.debug("Seeded %d existing PR entries from artifact", len(pull_requests))
                except (FileNotFoundError, ValueError) as e:
                    logger.debug("Could not load existing gh-pull-request artifact: %s", e)

            affected_repos = get_affected_repo_paths(context)
            if not affected_repos:
                logger.info("No affected repos — skipping PR creation")
                # Seeded entries from a prior run are intentionally discarded here.
                # When no repos are affected, there is nothing to publish and the
                # artifact is written as an empty skip record.
                artifact = GhPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=[],
                    platform="github",
                )
                context.artifact_store.write_artifact(artifact)
                return StepResult.ok(None)

            for repo_path in affected_repos:
                self._process_repo(
                    context, repo_path, title, summary, pull_requests, env, attachment_md
                )

            # Emit artifact comment and progress comment after all repos are processed
            if pull_requests:
                artifact = GhPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=pull_requests,
                    platform="github",
                )
                status, msg = emit_artifact_comment(
                    context.require_issue_id, context.adw_id, artifact
                )
                log_artifact_comment_status(status, msg)

                pr_urls = [entry.url for entry in pull_requests]
                comment_data = {
                    "commits": pr_details.get("commits", []),
                    "output": "pull-request-created",
                    "urls": pr_urls,
                }
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    f"Pull request(s) created: {', '.join(pr_urls)}",
                    comment_data,
                )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "gh pr create timed out after 120 seconds"
            logger.warning(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pull-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating pull request: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pull-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
