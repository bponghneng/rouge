"""Update PR/MR with new commits step implementation."""

import json
import logging
import os
import re
import subprocess
import traceback
from typing import Any, Optional, Tuple

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.shared import AGENT_COMMIT_COMPOSER, get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Required fields for compose-commits output JSON
COMPOSE_COMMITS_REQUIRED_FIELDS = {"output": str}

# Max characters to log from LLM response
MAX_LOG_LENGTH = 500


def _sanitize_for_logging(text: Optional[str], max_length: int = MAX_LOG_LENGTH) -> str:
    """Sanitize text by redacting secrets and truncating to safe length.

    Redacts common secret patterns (API keys, tokens, emails) and truncates
    to max_length characters to prevent logging of sensitive/verbose content.

    Pattern matching is intentionally conservative to err on the side of safety.
    The final catch-all pattern may redact some non-sensitive data (e.g., hashes),
    but this trade-off is acceptable given the security risk of logging secrets.

    Args:
        text: Text to sanitize (None is converted to "[None]")
        max_length: Maximum length of returned string

    Returns:
        Sanitized and truncated text safe for logging
    """
    if text is None:
        return "[None]"

    # Redact common secret patterns
    sanitized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)
    # GitHub tokens: prefix + 36-40 chars (ghp_, gho_, ghu_, ghs_, ghr_)
    sanitized = re.sub(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b", "[GITHUB_TOKEN]", sanitized)
    # GitLab tokens: prefix + 20+ chars (glpat-, gldt-, gloas-, glcbt-)
    sanitized = re.sub(
        r"\b(?:glpat|gldt|gloas|glcbt)-[A-Za-z0-9_-]{20,}\b", "[GITLAB_TOKEN]", sanitized
    )
    # OpenAI-style API keys: sk- prefix
    sanitized = re.sub(r"\bsk-[A-Za-z0-9]{20,}\b", "[API_KEY]", sanitized)
    # Generic long alphanumeric tokens (catch-all for safety)
    sanitized = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[TOKEN]", sanitized)

    # Truncate if longer than max_length
    if len(sanitized) > max_length:
        return sanitized[:max_length] + "..."
    return sanitized


def _emit_and_log(issue_id: int, adw_id: str, text: str, raw: dict[str, Any]) -> None:
    """Helper to emit comment and log based on status.

    Args:
        issue_id: Issue ID
        adw_id: ADW ID
        text: Comment text
        raw: Raw payload data
    """
    payload = CommentPayload(
        issue_id=issue_id,
        adw_id=adw_id,
        text=text,
        raw=raw,
        source="system",
        kind="workflow",
    )
    status, msg = emit_comment_from_payload(payload)
    if status == "success":
        logger.debug(msg)
    elif status == "skipped":
        logger.info(msg)
    else:
        logger.error(msg)


class UpdatePRCommitsStep(WorkflowStep):
    """Push new commits to an existing pull request or merge request.

    This step is used in patch workflows to add new commits to an existing
    PR/MR. It does not create new PRs/MRs.

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

    def _detect_pr_platform(self, repo_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Detect the existing PR/MR platform and URL using git CLI tools.

        Uses DEV_SEC_OPS_PLATFORM to select either GitHub or GitLab and
        invokes the corresponding CLI. If the env var is missing or invalid,
        returns (None, None).

        Args:
            repo_path: Path to the repository root

        Returns:
            Tuple of (platform, url) where platform is "github" or "gitlab",
            or (None, None) if no PR/MR is detected or no CLI tool is available.
        """
        platform = os.environ.get("DEV_SEC_OPS_PLATFORM", "").lower()
        if platform not in {"github", "gitlab"}:
            logger.warning(
                "DEV_SEC_OPS_PLATFORM is not set to a supported platform (github/gitlab)"
            )
            return (None, None)

        if platform == "github":
            github_pat = os.environ.get("GITHUB_PAT")
            env = os.environ.copy()
            if github_pat:
                env["GH_TOKEN"] = github_pat

            try:
                result = subprocess.run(
                    ["gh", "pr", "view", "--json", "url"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                    cwd=repo_path,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    url = data.get("url", "")
                    if url:
                        logger.debug("Detected GitHub PR: %s", url)
                        return ("github", url)
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
                    if url:
                        logger.debug("Detected GitLab MR: %s", url)
                        return ("gitlab", url)
            except (
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                OSError,
                subprocess.SubprocessError,
            ):
                logger.debug("glab mr view failed or timed out")

        return (None, None)

    def run(self, context: WorkflowContext) -> StepResult:
        """Push new commits to an existing PR/MR.

        Detects the PR/MR platform by running the CLI indicated by
        DEV_SEC_OPS_PLATFORM rather than loading artifacts from a parent workflow.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        repo_path = get_repo_path()

        # Compose conventional commits from unstaged changes
        try:
            handler = make_progress_comment_handler(context.require_issue_id, context.adw_id)

            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_COMMIT_COMPOSER,
                slash_command="/adw-compose-commits",
                args=[],
                adw_id=context.adw_id,
                issue_id=context.require_issue_id,
                model="sonnet",
            )

            logger.debug(
                "compose_commits request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            response = execute_template(request, stream_handler=handler)

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
                sanitized_error = _sanitize_for_logging(parse_result.error)
                error_msg = sanitized_error or "Compose commits JSON parsing failed"
                logger.warning("Compose commits JSON parsing failed: %s", error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "compose-commits-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            logger.info("Commits composed successfully")
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

        # Detect platform and PR/MR URL
        platform, pr_url = self._detect_pr_platform(repo_path)

        if not platform or not pr_url:
            error_msg = "No existing PR/MR found for patch update"
            logger.warning(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)

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
            skip_msg = f"PR update skipped: {pat_name} environment variable not set"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pr-update-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        try:
            # Execute with appropriate token environment variable
            env = os.environ.copy()
            env[token_env_var] = pat

            # Check if we're on a branch (not in detached HEAD state)
            branch_check = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_path,
            )

            if branch_check.returncode != 0:
                error_msg = "Cannot push: not on a branch (detached HEAD state)"
                logger.error(error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            branch = branch_check.stdout.strip()
            logger.debug("On branch: %s", branch)

            # Push commits to origin (the PR/MR will automatically update)
            push_cmd = ["git", "push", "origin", branch]
            logger.debug("Pushing patch commits to origin...")

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
                    f"git push failed (exit code {push_result.returncode}): "
                    f"{push_result.stderr}"
                )
                logger.warning(error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            logger.info("Patch commits pushed to PR/MR: %s", pr_url)

            # Emit progress comment indicating commits were added
            comment_msg = "Commits pushed to branch"
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                comment_msg,
                {
                    "output": "pr-updated",
                    "url": pr_url,
                    "platform": platform,
                },
            )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "git push timed out after 60 seconds"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except (OSError, PermissionError, ValueError, subprocess.SubprocessError) as e:
            error_msg = f"Error updating PR/MR with patch commits: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception:
            # Re-raise unexpected exceptions after logging
            logger.exception("Unexpected error updating PR/MR")
            raise
