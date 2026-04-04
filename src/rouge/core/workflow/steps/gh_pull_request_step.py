"""Create GitHub pull request step implementation."""

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Optional

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ComposeRequestArtifact,
    GhPullRequestArtifact,
    PullRequestEntry,
)
from rouge.core.workflow.repo_filter import get_affected_repos
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import has_commits_ahead_of_base
from rouge.core.workflow.types import StepResult


class GhPullRequestStep(WorkflowStep):
    """Create GitHub pull request via gh CLI."""

    @property
    def name(self) -> str:
        return "Creating GitHub pull request"

    @property
    def is_critical(self) -> bool:
        # PR creation is best-effort - workflow continues on failure
        return False

    def _validate_prerequisites(
        self, context: WorkflowContext, logger: logging.Logger
    ) -> tuple[Optional[dict], Optional[StepResult]]:
        """Validate all prerequisites for PR creation.

        Args:
            context: Workflow context
            logger: Logger instance

        Returns:
            Tuple of (pr_details, early_return). If early_return is not None,
            the caller should return it immediately. Otherwise pr_details is valid.
        """

        def _skip(msg: str) -> StepResult:
            logger.info(msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=msg,
                raw={"output": "pull-request-skipped", "reason": msg},
                source="system",
                kind="workflow",
            )
            status, comment_msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(comment_msg)
            else:
                logger.error(comment_msg)
            return StepResult.ok(None)

        pr_details = context.load_optional_artifact(
            "pr_details",
            "compose-request",
            ComposeRequestArtifact,
            lambda a: {"title": a.title, "summary": a.summary, "commits": a.commits},
        )

        if not pr_details:
            return None, _skip("PR creation skipped: no PR details in context")

        if not pr_details.get("title", ""):
            return None, _skip("PR creation skipped: PR title is empty")

        if not os.environ.get("GITHUB_PAT"):
            return None, _skip("PR creation skipped: GITHUB_PAT environment variable not set")

        if not shutil.which("gh"):
            logger.debug("Current PATH: %s", os.environ.get("PATH", ""))
            return None, _skip("PR creation skipped: gh CLI not found in PATH")

        return pr_details, None

    def _process_repo(
        self,
        repo_path: str,
        title: str,
        summary: str,
        env: dict,
        pull_requests: list[PullRequestEntry],
        context: WorkflowContext,
        logger: logging.Logger,
    ) -> None:
        """Process a single repository: adopt existing PR or push and create a new one.

        Modifies pull_requests in place and persists the artifact incrementally.

        Args:
            repo_path: Absolute path to the repository.
            title: PR title.
            summary: PR body / summary.
            env: Environment dict with GH_TOKEN set.
            pull_requests: Running list of PR entries (mutated in place).
            context: Workflow context.
            logger: Logger instance.
        """
        repo_name = os.path.basename(repo_path)

        # Layer 1: Already done check — skip if this repo_path is already recorded
        if any(entry.repo_path == repo_path for entry in pull_requests):
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
        if branch_name:
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
                            return
            except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                logger.debug("Could not check for existing PR in %s: %s", repo_path, e)

        # Check if branch has meaningful delta vs base
        if not has_commits_ahead_of_base(repo_path, logger):
            logger.info(
                "Skipping PR/MR creation for %s: no commits ahead of base",
                repo_name,
            )
            return

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
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
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

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitHub pull request using gh CLI.

        Validates prerequisites, loads artifacts, iterates affected repos,
        persists progress, and emits a summary comment.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Validate — returns early if any prerequisite is missing
        pr_details, early_return = self._validate_prerequisites(context, logger)
        if early_return is not None:
            return early_return

        assert pr_details is not None  # guaranteed by _validate_prerequisites
        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        try:
            # Execute with GH_TOKEN environment variable
            env = os.environ.copy()
            env["GH_TOKEN"] = os.environ["GITHUB_PAT"]

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

            # Filter repos to affected ones if implement artifact is available
            affected_repos, _implement_data = get_affected_repos(context)
            target_repos = affected_repos if _implement_data is not None else context.repo_paths

            # Iterate — delegate per-repo work to _process_repo
            for repo_path in target_repos:
                self._process_repo(repo_path, title, summary, env, pull_requests, context, logger)

            # Persist final artifact and emit summary comment
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
                payload = CommentPayload(
                    issue_id=context.require_issue_id,
                    adw_id=context.adw_id,
                    text=f"Pull request(s) created: {', '.join(pr_urls)}",
                    raw=comment_data,
                    source="system",
                    kind="workflow",
                )
                status, msg = emit_comment_from_payload(payload)
                if status == "success":
                    logger.debug(msg)
                else:
                    logger.error(msg)

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "gh pr create timed out after 120 seconds"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.exception(msg)
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating pull request: {e}"
            logger.exception(error_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
