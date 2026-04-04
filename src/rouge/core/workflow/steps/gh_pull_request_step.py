"""Create GitHub pull request step implementation."""

import json
import os
import re
import shutil
import subprocess

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

        if not pr_details:
            skip_msg = "PR creation skipped: no PR details in context"
            logger.info(skip_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.ok(None)

        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        if not title:
            skip_msg = "PR creation skipped: PR title is empty"
            logger.info(skip_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.ok(None)

        # Check for GITHUB_PAT environment variable
        github_pat = os.environ.get("GITHUB_PAT")
        if not github_pat:
            skip_msg = "PR creation skipped: GITHUB_PAT environment variable not set"
            logger.info(skip_msg)
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.ok(None)

        # Proactively check for gh CLI availability
        if not shutil.which("gh"):
            skip_msg = "PR creation skipped: gh CLI not found in PATH"
            logger.info(skip_msg)
            logger.debug("Current PATH: %s", os.environ.get("PATH", ""))
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text=skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.ok(None)

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

            # Filter repos to affected ones if implement artifact is available
            affected_repos, _implement_data = get_affected_repos(context)
            target_repos = affected_repos if affected_repos else context.repo_paths

            for repo_path in target_repos:
                repo_name = os.path.basename(repo_path)

                # Layer 1: Already done check — skip if this repo_path is already recorded
                already_done = any(entry.repo_path == repo_path for entry in pull_requests)
                if already_done:
                    logger.info(
                        "PR for repo %s (%s) already recorded, skipping",
                        repo_name,
                        repo_path,
                    )
                    continue

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
                    logger.debug(
                        "Checking for existing PR: %s (cwd=%s)", " ".join(list_cmd), repo_path
                    )
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
                                    continue
                    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                        logger.debug("Could not check for existing PR in %s: %s", repo_path, e)

                # Check if branch has meaningful delta vs base
                try:
                    base_branch_result = subprocess.run(
                        ["git", "rev-parse", "--verify", "--quiet", "origin/HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=repo_path,
                    )
                    base_ref = (
                        base_branch_result.stdout.strip()
                        if base_branch_result.returncode == 0
                        else "HEAD~1"
                    )
                    ahead_result = subprocess.run(
                        ["git", "rev-list", "--count", f"{base_ref}..HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=repo_path,
                    )
                    ahead_count = (
                        int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0
                    )
                    if ahead_count == 0:
                        logger.info(
                            "Skipping PR/MR creation for %s: no commits ahead of base",
                            repo_name,
                        )
                        continue
                except (subprocess.TimeoutExpired, OSError, ValueError):
                    pass  # Proceed with PR/MR creation if check fails

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
                    # Continue to next repo; partial progress is already saved
                    continue

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
