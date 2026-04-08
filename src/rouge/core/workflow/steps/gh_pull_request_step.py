"""Create GitHub pull request step implementation."""

import logging
import os
import re
import shutil
import subprocess
from typing import ClassVar

from rouge.core.utils import get_logger
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
    platform: ClassVar[str] = "github"
    entity_name: ClassVar[str] = "PR"
    entity_prefix: ClassVar[str] = "#"
    output_key_prefix: ClassVar[str] = "pull-request"

    @property
    def name(self) -> str:
        return "Creating GitHub pull request"

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
