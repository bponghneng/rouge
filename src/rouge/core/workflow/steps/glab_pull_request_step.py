"""Create GitLab merge request step implementation."""

import json
import re
import subprocess
from typing import ClassVar

from rouge.core.utils import get_logger
from rouge.core.workflow.pull_request_step_base import PullRequestStepBase

_logger = get_logger(__name__)


def _post_glab_attachment_note(
    repo_path: str,
    mr_number: int,
    body: str,
    env: dict[str, str],
) -> None:
    """Post or update the Rouge review-context note on a GitLab MR."""
    marker = "<!-- rouge-review-context -->"
    tagged_body = f"{marker}\n{body}"

    list_cmd = [
        "glab",
        "api",
        f"projects/:id/merge_requests/{mr_number}/notes?per_page=100",
    ]
    result = subprocess.run(
        list_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
    )

    existing_note_id = None
    if result.returncode == 0 and result.stdout.strip():
        try:
            notes = json.loads(result.stdout)
            for note in notes:
                if note.get("body", "").startswith(marker):
                    existing_note_id = note["id"]
                    break
        except (ValueError, KeyError):
            pass

    if existing_note_id:
        update_cmd = [
            "glab",
            "api",
            "--method",
            "PUT",
            f"projects/:id/merge_requests/{mr_number}/notes/{existing_note_id}",
            "-f",
            f"body={tagged_body}",
        ]
        update_result = subprocess.run(
            update_cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if update_result.returncode != 0:
            _logger.warning(
                "Failed to update review-context note on MR !%d: %s",
                mr_number,
                update_result.stderr,
            )
        else:
            _logger.info("Updated review-context note on MR !%d", mr_number)
    else:
        cmd = ["glab", "mr", "note", str(mr_number), "--message", tagged_body]
        create_result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=repo_path, env=env, timeout=30
        )
        if create_result.returncode != 0:
            _logger.warning(
                "Failed to post review-context note on MR !%d: %s",
                mr_number,
                create_result.stderr,
            )
        else:
            _logger.info("Posted review-context note on MR !%d", mr_number)


class GlabPullRequestStep(PullRequestStepBase):
    """Create GitLab merge request via glab CLI."""

    cli_binary: ClassVar[str] = "glab"
    pat_env_var: ClassVar[str] = "GITLAB_PAT"
    token_env_key: ClassVar[str] = "GITLAB_TOKEN"
    artifact_slug: ClassVar[str] = "glab-pull-request"
    platform: ClassVar[str] = "gitlab"
    entity_name: ClassVar[str] = "MR"
    entity_prefix: ClassVar[str] = "!"
    output_key_prefix: ClassVar[str] = "merge-request"

    @property
    def name(self) -> str:
        return "Creating GitLab merge request"

    def _list_cmd_args(self, branch_name: str) -> list[str]:
        return ["glab", "mr", "list", "--source-branch", branch_name, "--output", "json"]

    def _parse_existing_item(self, item: dict) -> tuple[str, int | None]:
        return (item.get("web_url", ""), item.get("iid"))

    def _create_cmd_args(self, title: str, summary: str, draft: bool) -> list[str]:
        cmd = ["glab", "mr", "create", "--title", title, "--description", summary]
        if draft:
            cmd.append("--draft")
        return cmd

    def _parse_create_output(self, stdout: str) -> tuple[str, int | None] | None:
        url_match = re.search(r"https?://\S+/merge_requests/\d+", stdout)
        if not url_match:
            return None
        url = url_match.group(0)
        number: int | None = None
        number_match = re.search(r"/merge_requests/(\d+)", url)
        if number_match:
            number = int(number_match.group(1))
        return (url, number)

    def _post_attachment(self, repo_path: str, number: int, body: str, env: dict[str, str]) -> None:
        _post_glab_attachment_note(repo_path, number, body, env)
