"""Create GitHub pull request step implementation."""

import json
import logging
import os
import re
import shutil
import subprocess

from rouge.core.notifications.comments import (
    emit_artifact_comment,
    log_artifact_comment_status,
)
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ComposeRequestArtifact,
    GhPullRequestArtifact,
    PullRequestEntry,
)
from rouge.core.workflow.shared import get_affected_repo_paths
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import _emit_and_log, load_and_render_attachment
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

    if existing_comment_id:
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


class GhPullRequestStep(WorkflowStep):
    """Create GitHub pull request via gh CLI."""

    @property
    def name(self) -> str:
        return "Creating GitHub pull request"

    @property
    def is_critical(self) -> bool:
        # PR creation is best-effort - workflow continues on failure
        return False

    def _check_preconditions(
        self,
        context: WorkflowContext,
        pr_details: dict | None,
        logger: logging.Logger,
    ) -> StepResult | None:
        """Validate preconditions for PR creation.

        Returns a StepResult if a precondition fails (caller should return it),
        or None if all checks pass.
        """
        if not pr_details:
            skip_msg = "PR creation skipped: no PR details in context"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        title = pr_details.get("title", "")

        if not title:
            skip_msg = "PR creation skipped: PR title is empty"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Check for GITHUB_PAT environment variable
        if not os.environ.get("GITHUB_PAT"):
            skip_msg = "PR creation skipped: GITHUB_PAT environment variable not set"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Proactively check for gh CLI availability
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

    def _try_adopt_existing(
        self,
        context: WorkflowContext,
        repo_path: str,
        branch_name: str,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
    ) -> bool:
        """Check for and adopt an existing GitHub PR for branch_name in repo_path.

        Returns True if an existing PR was adopted (caller should skip Layer 3),
        False otherwise.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(repo_path)
        list_cmd = [
            "gh",
            "pr",
            "list",
            "--head",
            branch_name,
            "--json",
            "url,number",
        ]
        logger.debug("Checking for existing PR: %s (cwd=%s)", " ".join(list_cmd), repo_path)
        try:
            list_result = subprocess.run(
                list_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )
            if list_result.returncode == 0 and list_result.stdout.strip():
                pr_list = json.loads(list_result.stdout.strip())
                if pr_list:
                    existing_pr = pr_list[0]
                    pr_url = existing_pr.get("url", "")
                    pr_number = existing_pr.get("number")
                    if pr_url:
                        logger.info(
                            "Adopting existing PR for repo %s: %s",
                            repo_name,
                            pr_url,
                        )
                        entry = PullRequestEntry(
                            repo=repo_name,
                            repo_path=repo_path,
                            url=pr_url,
                            number=pr_number,
                            adopted=True,
                        )
                        pull_requests.append(entry)
                        context.artifact_store.write_artifact(
                            GhPullRequestArtifact(
                                workflow_id=context.adw_id,
                                pull_requests=pull_requests,
                                platform="github",
                            )
                        )
                        logger.debug(
                            "Saved gh-pull-request artifact after adopting PR for %s",
                            repo_name,
                        )
                        if attachment_md and entry.number:
                            try:
                                _post_gh_attachment_comment(
                                    repo_path=repo_path,
                                    pr_number=entry.number,
                                    body=attachment_md,
                                    env=env,
                                )
                            except (
                                subprocess.TimeoutExpired,
                                OSError,
                            ) as exc:
                                logger.warning(
                                    "Failed to post attachment comment on PR #%d: %s",
                                    entry.number,
                                    exc,
                                )
                        return True
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.debug("Could not check for existing PR in %s: %s", repo_path, e)
        return False

    def _process_repo(
        self,
        context: WorkflowContext,
        repo_path: str,
        title: str,
        summary: str,
        pull_requests: list[PullRequestEntry],
        env: dict[str, str],
        attachment_md: str | None,
    ) -> None:
        """Process a single repository for PR creation.

        Checks for existing PRs, pushes the branch, and creates a new PR.
        Mutates *pull_requests* in-place when a PR is adopted or created.
        """
        logger = get_logger(context.adw_id)
        repo_name = os.path.basename(repo_path)

        # Layer 1: Already done check — skip if this repo_path is already recorded
        already_done = any(entry.repo_path == repo_path for entry in pull_requests)
        if already_done:
            logger.info(
                "PR for repo %s (%s) already recorded, skipping",
                repo_name,
                repo_path,
            )
            return

        # Determine the current branch name for this repo
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=repo_path,
        )
        branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

        # Layer 2: Adopt existing remote PR if one already exists for this branch
        if branch_name and self._try_adopt_existing(
            context, repo_path, branch_name, pull_requests, env, attachment_md
        ):
            return

        # Layer 2.5: Branch-delta guard — skip PR creation if no commits ahead of base
        try:
            base_branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
            base_branch = (
                base_branch_result.stdout.strip().replace("origin/", "")
                if base_branch_result.returncode == 0
                else "main"
            )
            delta_result = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD...origin/{base_branch}"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=30,
            )
            if delta_result.returncode == 0 and delta_result.stdout.strip() == "0":
                logger.info("No commits ahead of base in %s — skipping PR creation", repo_path)
                return
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(
                "Branch-delta check failed for %s: %s, continuing with PR creation",
                repo_path,
                e,
            )

        # Layer 3: Push + create new PR
        push_cmd = ["git", "push", "--set-upstream", "origin", "HEAD"]
        logger.debug("Pushing current branch to origin in %s...", repo_path)
        try:
            push_result = subprocess.run(
                push_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )
            if push_result.returncode == 0:
                logger.debug("Branch pushed successfully for %s", repo_name)
            else:
                logger.debug(
                    "git push failed for %s (exit code %d): %s",
                    repo_name,
                    push_result.returncode,
                    push_result.stderr,
                )
        except subprocess.TimeoutExpired:
            logger.debug("git push timed out for %s, continuing to PR creation", repo_name)
        except OSError as e:
            logger.exception("git push failed for %s: %s", repo_name, e)
            raise

        cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            summary,
        ]

        if context.pipeline_type == "thin":
            cmd.append("--draft")

        logger.debug("Executing: %s (cwd=%s)", " ".join(cmd), repo_path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            cwd=repo_path,
        )

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
        commits = pr_details.get("commits", [])
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
                    "commits": commits,
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
