"""Create GitHub pull request step implementation."""

import logging
import os
import re
import shutil
from typing import ClassVar

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ArtifactType,
    GhPullRequestArtifact,
    PullRequestArtifactBase,
)
from rouge.core.workflow.pull_request_step_base import PullRequestStepBase
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.step_utils import _emit_and_log, post_gh_attachment_comment
from rouge.core.workflow.types import StepResult

_logger = get_logger(__name__)


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
        post_gh_attachment_comment(repo_path, number, body, env)
