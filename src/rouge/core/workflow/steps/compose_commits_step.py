"""Update PR/MR with new commits step implementation."""

import json
import os
import subprocess
import traceback
from typing import Dict, List, Optional, Tuple

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import ComposeCommitsArtifact, ComposeCommitsRepoResult
from rouge.core.workflow.shared import AGENT_COMMIT_COMPOSER, get_affected_repo_paths
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import (
    _emit_and_log,
    _sanitize_for_logging,
    coerce_repos,
    load_and_render_patch_attachment,
    post_gh_attachment_comment,
    post_glab_attachment_note,
)
from rouge.core.workflow.types import StepResult

# Required fields for compose-commits output JSON
COMPOSE_COMMITS_REQUIRED_FIELDS = {"output": str, "repos": list}

# JSON schema generated from the Pydantic submodel so the LLM-facing schema and
# the artifact model stay in sync automatically.  Generated once at import time.
_REPO_SCHEMA = ComposeCommitsRepoResult.model_json_schema()
COMPOSE_COMMITS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "output": {"type": "string", "const": "compose-commits"},
            "repos": {
                "type": "array",
                "items": _REPO_SCHEMA,
            },
        },
        "required": ["output", "repos"],
    },
    indent=2,
)


class ComposeCommitsStep(WorkflowStep):
    """Compose commits and push to an existing pull request or merge request.

    This step is used in patch workflows to compose and add new commits to an
    existing PR/MR. It does not create new PRs/MRs.

    Platform detection is driven by ``DEV_SEC_OPS_PLATFORM`` and uses the
    corresponding git CLI tool (``gh`` for GitHub, ``glab`` for GitLab).
    """

    @property
    def name(self) -> str:
        return "Updating pull request with patch commits"

    @property
    def is_critical(self) -> bool:
        # PR update is best-effort - workflow continues on failure
        return False

    def _detect_pr_platform(
        self, repo_path: str, adw_id: str
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Detect the existing PR/MR platform, URL, and number using git CLI tools.

        Uses DEV_SEC_OPS_PLATFORM to select either GitHub or GitLab and
        invokes the corresponding CLI. If the env var is missing or invalid,
        returns (None, None, None).

        Args:
            repo_path: Path to the repository root
            adw_id: Workflow ID for logger retrieval

        Returns:
            Tuple of (platform, url, number) where platform is "github" or
            "gitlab" and number is the PR/MR number (int), or
            (None, None, None) if no PR/MR is detected or no CLI tool is
            available.
        """
        logger = get_logger(adw_id)
        platform = os.environ.get("DEV_SEC_OPS_PLATFORM", "").lower()
        if platform not in {"github", "gitlab"}:
            logger.warning(
                "DEV_SEC_OPS_PLATFORM is not set to a supported platform (github/gitlab)"
            )
            return (None, None, None)

        if platform == "github":
            github_pat = os.environ.get("GITHUB_PAT")
            env = os.environ.copy()
            if github_pat:
                env["GH_TOKEN"] = github_pat

            try:
                result = subprocess.run(
                    ["gh", "pr", "view", "--json", "url,number"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                    cwd=repo_path,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    url = data.get("url", "")
                    number = data.get("number")
                    if not (isinstance(number, int) and number > 0):
                        number = None
                    if url:
                        logger.debug("Detected GitHub PR: %s (#%s)", url, number)
                        return ("github", url, number)
            except (
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                OSError,
                subprocess.SubprocessError,
            ):
                logger.debug("gh pr view failed or timed out")
        else:
            gitlab_pat = os.environ.get("GITLAB_PAT")
            env = os.environ.copy()
            if gitlab_pat:
                env["GITLAB_TOKEN"] = gitlab_pat

            try:
                result = subprocess.run(
                    ["glab", "mr", "view", "--output", "json"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                    cwd=repo_path,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    url = data.get("web_url", "")
                    number = data.get("iid")
                    if not (isinstance(number, int) and number > 0):
                        number = None
                    if url:
                        logger.debug("Detected GitLab MR: %s (!%s)", url, number)
                        return ("gitlab", url, number)
            except (
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                OSError,
                subprocess.SubprocessError,
            ):
                logger.debug("glab mr view failed or timed out")

        return (None, None, None)

    def _push_repo(
        self,
        repo_path: str,
        env: Dict[str, str],
        adw_id: str,
        issue_id: int,
    ) -> StepResult:
        """Push commits to origin for a single repository.

        Checks that the repo is on a named branch, then runs
        ``git push origin <branch>``.

        Args:
            repo_path: Path to the repository root.
            env: Environment dict with the appropriate token set.
            adw_id: Workflow ID for logger retrieval.
            issue_id: Issue ID for progress comments.

        Returns:
            StepResult indicating success or failure for this repo.
        """
        logger = get_logger(adw_id)

        try:
            # Check if we're on a branch (not in detached HEAD state)
            branch_check = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=repo_path,
            )

            if branch_check.returncode != 0:
                error_msg = f"Cannot push {repo_path}: not on a branch (detached HEAD state)"
                logger.error(error_msg)
                _emit_and_log(
                    issue_id,
                    adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg, "repo": repo_path},
                )
                return StepResult.fail(error_msg)

            branch = branch_check.stdout.strip()
            logger.debug("On branch: %s (repo: %s)", branch, repo_path)

            # Push commits to origin (the PR/MR will automatically update)
            push_cmd = ["git", "push", "origin", branch]
            logger.debug("Pushing patch commits to origin for %s...", repo_path)

            push_result = subprocess.run(
                push_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )

            if push_result.returncode != 0:
                error_msg = (
                    f"git push failed for {repo_path} "
                    f"(exit code {push_result.returncode}): "
                    f"{push_result.stderr}"
                )
                logger.warning(error_msg)
                _emit_and_log(
                    issue_id,
                    adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg, "repo": repo_path},
                )
                return StepResult.fail(error_msg)

            logger.info("Patch commits pushed for repo: %s", repo_path)
            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = f"git push timed out after 60 seconds for {repo_path}"
            logger.exception(error_msg)
            _emit_and_log(
                issue_id,
                adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg, "repo": repo_path},
            )
            return StepResult.fail(error_msg)
        except (OSError, PermissionError, ValueError, subprocess.SubprocessError) as e:
            error_msg = f"Error updating PR/MR with patch commits for {repo_path}: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                issue_id,
                adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg, "repo": repo_path},
            )
            return StepResult.fail(error_msg)

    def _compose_commits(self, context: WorkflowContext) -> Optional[StepResult]:
        """Compose conventional commits from unstaged changes via the LLM agent.

        Returns ``None`` on success (caller should continue) or a
        :class:`StepResult` on failure (caller should return it immediately).
        """
        logger = get_logger(context.adw_id)

        try:
            repo_paths = get_affected_repo_paths(context)
            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_COMMIT_COMPOSER,
                prompt_id=PromptId.COMPOSE_COMMITS,
                args=repo_paths,
                adw_id=context.adw_id,
                issue_id=context.require_issue_id,
                model="sonnet",
                json_schema=COMPOSE_COMMITS_JSON_SCHEMA,
            )

            logger.debug(
                "compose_commits request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            response = execute_template(request)

            logger.debug("compose_commits response: success=%s", response.success)
            logger.debug("Compose commits LLM response: %s", _sanitize_for_logging(response.output))

            if not response.success:
                sanitized_output = _sanitize_for_logging(response.output)
                error_msg = f"Compose commits failed: {sanitized_output}"
                logger.warning(error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "compose-commits-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output,
                COMPOSE_COMMITS_REQUIRED_FIELDS,
                step_name="compose_commits",
            )
            if not parse_result.success:
                raw_error = parse_result.error or "Compose commits JSON parsing failed"
                sanitized_error = _sanitize_for_logging(raw_error)
                error_msg = sanitized_error or raw_error
                logger.warning("Compose commits JSON parsing failed: %s", error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "compose-commits-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            logger.info("Commits composed successfully")

            # Save artifact to the artifact store
            if parse_result.data is not None:
                valid_repos = coerce_repos(
                    parse_result.data,
                    ComposeCommitsRepoResult,
                    "compose_commits",
                    logger,
                )
                artifact = ComposeCommitsArtifact(
                    workflow_id=context.adw_id,
                    repos=valid_repos,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved compose_commits artifact for workflow %s", context.adw_id)

                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                log_artifact_comment_status(status, msg)

            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                "Commits composed successfully.",
                {"output": "compose-commits-done", "result": parse_result.data},
            )

        except Exception as e:
            sanitized_error = _sanitize_for_logging(str(e))
            error_msg = f"Compose commits failed: {sanitized_error}"
            tb = _sanitize_for_logging(traceback.format_exc())
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "compose-commits-failed", "error": error_msg, "traceback": tb},
            )
            return StepResult.fail(error_msg)

        return None

    def _push_all_repos(
        self,
        context: WorkflowContext,
        attachment_md: str | None,
    ) -> StepResult:
        """Detect PR/MR platform for each repo and push commits.

        Posts the review-context attachment after each successful push when
        *attachment_md* is not ``None``.
        """
        logger = get_logger(context.adw_id)
        issue_id = context.require_issue_id
        succeeded: List[str] = []
        errors: List[str] = []

        for repo_path in context.repo_paths:
            # Detect platform and PR/MR URL for this repo
            platform, pr_url, pr_number = self._detect_pr_platform(repo_path, context.adw_id)

            if not platform or not pr_url:
                warn_msg = f"No existing PR/MR found for {repo_path}, skipping push"
                logger.warning(warn_msg)
                _emit_and_log(
                    issue_id,
                    context.adw_id,
                    warn_msg,
                    {"output": "pr-update-skipped", "reason": warn_msg, "repo": repo_path},
                )
                errors.append(warn_msg)
                continue

            # Determine which PAT to use based on detected platform
            if platform == "github":
                pat = os.environ.get("GITHUB_PAT")
                pat_name = "GITHUB_PAT"
                token_env_var = "GH_TOKEN"
            else:  # gitlab
                pat = os.environ.get("GITLAB_PAT")
                pat_name = "GITLAB_PAT"
                token_env_var = "GITLAB_TOKEN"

            if not pat:
                skip_msg = (
                    f"PR update skipped for {repo_path}: {pat_name} environment variable not set"
                )
                logger.info(skip_msg)
                _emit_and_log(
                    issue_id,
                    context.adw_id,
                    skip_msg,
                    {"output": "pr-update-skipped", "reason": skip_msg, "repo": repo_path},
                )
                errors.append(skip_msg)
                continue

            env = os.environ.copy()
            env[token_env_var] = pat

            push_result = self._push_repo(repo_path, env, context.adw_id, issue_id)

            if push_result.success:
                succeeded.append(repo_path)
                comment_msg = f"Commits pushed to branch for {repo_path}"
                _emit_and_log(
                    issue_id,
                    context.adw_id,
                    comment_msg,
                    {
                        "output": "pr-updated",
                        "url": pr_url,
                        "platform": platform,
                        "repo": repo_path,
                    },
                )
                # Post/update review-context comment (best-effort)
                if attachment_md and pr_number:
                    try:
                        if platform == "github":
                            post_gh_attachment_comment(repo_path, pr_number, attachment_md, env)
                        else:
                            post_glab_attachment_note(repo_path, pr_number, attachment_md, env)
                    except Exception:
                        logger.error(
                            "Failed to post review-context on %s for %s",
                            platform,
                            repo_path,
                            exc_info=True,
                        )
            else:
                errors.append(push_result.error or f"Push failed for {repo_path}")

        # Return ok if at least one repo pushed successfully
        if succeeded:
            logger.info(
                "Pushed commits for %d/%d repos: %s",
                len(succeeded),
                len(context.repo_paths),
                succeeded,
            )
            return StepResult.ok(None)

        # All repos failed
        combined = "; ".join(errors)
        error_msg = f"All repo pushes failed: {combined}"
        logger.warning(error_msg)
        _emit_and_log(
            issue_id,
            context.adw_id,
            error_msg,
            {"output": "pr-update-failed", "error": error_msg},
        )
        return StepResult.fail(error_msg)

    def run(self, context: WorkflowContext) -> StepResult:
        """Push new commits to existing PR/MRs across all repos.

        Detects the PR/MR platform by running the CLI indicated by
        DEV_SEC_OPS_PLATFORM rather than loading artifacts from a parent workflow.
        Iterates over all repos in ``context.repo_paths`` and pushes each one
        independently.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Compose conventional commits from unstaged changes
        compose_failure = self._compose_commits(context)
        if compose_failure is not None:
            return compose_failure

        # Render review-context attachment once (best-effort, never blocks workflow)
        attachment_md: str | None = None
        try:
            attachment_md = load_and_render_patch_attachment(context)
        except Exception:
            logger.error("Failed to render patch review-context attachment", exc_info=True)

        return self._push_all_repos(context, attachment_md)
