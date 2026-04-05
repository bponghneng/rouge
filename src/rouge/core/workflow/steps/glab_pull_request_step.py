"""Create GitLab merge request step implementation."""

import json
import re
import subprocess
from typing import ClassVar

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ArtifactType,
    GlabPullRequestArtifact,
    PullRequestArtifactBase,
)
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
        cmd = ["glab", "mr", "note", "create", str(mr_number), "--message", tagged_body]
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
    artifact_slug: ClassVar[ArtifactType] = "glab-pull-request"
    platform: ClassVar[str] = "gitlab"
    entity_name: ClassVar[str] = "MR"
    entity_prefix: ClassVar[str] = "!"
    output_key_prefix: ClassVar[str] = "merge-request"

    @property
    def name(self) -> str:
        return "Creating GitLab merge request"

    @property
    def artifact_class(self) -> type[PullRequestArtifactBase]:
        return GlabPullRequestArtifact

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

        # Write artifact after each repo so partial progress survives failures
        artifact = GlabPullRequestArtifact(
            workflow_id=context.adw_id,
            pull_requests=pull_requests,
            platform="gitlab",
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved glab-pull-request artifact after creating MR for %s", repo_name)

        if attachment_md and entry.number:
            try:
                _post_glab_attachment_note(
                    repo_path=repo_path,
                    mr_number=entry.number,
                    body=attachment_md,
                    env=env,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning(
                    "Failed to post attachment note on MR !%d: %s",
                    entry.number,
                    exc,
                )

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitLab merge request using glab CLI.

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
        gitlab_pat = os.environ.get("GITLAB_PAT", "")

        try:
            # Execute with GITLAB_TOKEN environment variable (glab uses GITLAB_TOKEN)
            env = os.environ.copy()
            env["GITLAB_TOKEN"] = gitlab_pat

            # Seed pull_requests from existing artifact for rerun continuity (Layer 0)
            pull_requests: list[PullRequestEntry] = []
            if context.artifact_store.artifact_exists("glab-pull-request"):
                try:
                    existing_artifact = context.artifact_store.read_artifact(
                        "glab-pull-request", GlabPullRequestArtifact
                    )
                    pull_requests = list(existing_artifact.pull_requests)
                    logger.debug("Seeded %d existing MR entries from artifact", len(pull_requests))
                except Exception as e:
                    logger.debug("Could not load existing glab-pull-request artifact: %s", e)

            affected_repos = get_affected_repo_paths(context)
            if not affected_repos:
                logger.info("No affected repos — skipping MR creation")
                # Seeded entries from a prior run are intentionally discarded here.
                # When no repos are affected, there is nothing to publish and the
                # artifact is written as an empty skip record.
                artifact = GlabPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=[],
                    platform="gitlab",
                )
                context.artifact_store.write_artifact(artifact)
                return StepResult.ok(None)

            for repo_path in affected_repos:
                self._process_repo(
                    context, repo_path, title, summary, pull_requests, env, attachment_md
                )

            # Emit artifact comment and progress comment after all repos are processed
            if pull_requests:
                artifact = GlabPullRequestArtifact(
                    workflow_id=context.adw_id,
                    pull_requests=pull_requests,
                    platform="gitlab",
                )
                status, msg = emit_artifact_comment(
                    context.require_issue_id, context.adw_id, artifact
                )
                log_artifact_comment_status(status, msg)

                mr_urls = [entry.url for entry in pull_requests]
                comment_data = {
                    "commits": pr_details.get("commits", []),
                    "output": "merge-request-created",
                    "urls": mr_urls,
                }
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    f"Merge request(s) created: {', '.join(mr_urls)}",
                    comment_data,
                )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "glab mr create timed out after 120 seconds"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "glab CLI not found, skipping MR creation"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating merge request: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "merge-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
