"""Review generation step implementation."""

import json
import os
import subprocess

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import CodeReviewArtifact, GitCheckoutArtifact, PlanArtifact
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ReviewData, StepResult

# Module-level constant for step name used in rerun_from references
CODE_REVIEW_STEP_NAME = "Generating CodeRabbit review"

# JSON schema for code review summary structured output
CODE_REVIEW_SUMMARY_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "output": { "type": "string", "const": "code-review-summary" },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["output", "summary"]
}"""


def is_clean_review(review_text: str) -> bool:
    """Determine whether a review indicates no actionable issues.

    A review is considered clean when it contains the phrase
    "Review completed" (signalling the reviewer finished successfully)
    **and** does not contain "File:" (which precedes per-file comments
    that require attention).

    Args:
        review_text: The full text output from the code review.

    Returns:
        True if the review is clean (no issues), False otherwise.
    """
    return "Review completed" in review_text and "File:" not in review_text


class CodeReviewStep(WorkflowStep):
    """Generate CodeRabbit review."""

    @property
    def name(self) -> str:
        return CODE_REVIEW_STEP_NAME

    @property
    def is_critical(self) -> bool:
        # Review generation is not critical - workflow continues if it fails
        return False

    def _parse_timeout_seconds(self, adw_id: str) -> int:
        """Parse CODERABBIT_TIMEOUT_SECONDS from environment with safe fallback.

        Args:
            adw_id: Workflow ID for logger retrieval

        Returns:
            Timeout in seconds, defaulting to 600 (10 minutes) if env var is
            missing or malformed.
        """
        logger = get_logger(adw_id)
        try:
            return int(os.getenv("CODERABBIT_TIMEOUT_SECONDS", "600"))
        except (ValueError, TypeError):
            logger.warning("Invalid CODERABBIT_TIMEOUT_SECONDS value, using default 600 seconds")
            return 600

    def _generate_review(
        self,
        repo_path: str,
        adw_id: str,
        base_commit: str | None = None,
    ) -> StepResult[ReviewData]:
        """Generate CodeRabbit review output.

        Args:
            repo_path: Repository root path where .coderabbit.yaml config is located
            adw_id: Workflow ID for logger retrieval
            base_commit: Optional base commit SHA for CodeRabbit --base-commit flag

        Returns:
            StepResult with ReviewData containing review text
        """
        logger = get_logger(adw_id)
        try:
            # Read timeout from environment variable with default of 600 seconds (10 minutes)
            timeout_seconds = self._parse_timeout_seconds(adw_id)

            # Build absolute config path and validate it exists (config must be in repo root)
            config_path = os.path.join(repo_path, ".coderabbit.yaml")
            if not os.path.exists(config_path):
                return StepResult.fail(f"CodeRabbit config not found at {config_path}")

            logger.info("Generating CodeRabbit review from %s", repo_path)
            logger.debug("Using CodeRabbit config at %s", config_path)
            logger.debug("CodeRabbit timeout: %s seconds", timeout_seconds)

            # Build CodeRabbit command
            # Note: Uses direct 'coderabbit --prompt-only' instead of
            # 'coderabbit review --prompt-only' to align with updated CLI interface
            cmd = [
                "coderabbit",
                "--prompt-only",
                "--config",
                config_path,
            ]

            if base_commit:
                cmd.extend(["--base-commit", base_commit])
                logger.debug("Using base commit: %s", base_commit)

            logger.debug("Executing CodeRabbit command: %s", " ".join(cmd))
            logger.debug("Running from directory: %s", repo_path)

            # Execute CodeRabbit review from repo_path
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, timeout=timeout_seconds
            )

            if result.returncode != 0:
                logger.error("CodeRabbit review failed with code %s", result.returncode)
                logger.error("stderr: %s", result.stderr)
                return StepResult.fail(f"CodeRabbit review failed with code {result.returncode}")

            review_text = result.stdout
            logger.info("CodeRabbit review generated (%s chars)", len(review_text))

            return StepResult.ok(ReviewData(review_text=review_text))

        except subprocess.TimeoutExpired:
            logger.exception("CodeRabbit review timed out after %s seconds", timeout_seconds)
            return StepResult.fail(f"CodeRabbit review timed out after {timeout_seconds} seconds")
        except Exception as e:
            logger.exception("Failed to generate review")
            return StepResult.fail(f"Failed to generate review: {e}")

    def _post_review_summary_to_pr(
        self,
        review_text: str,
        pr_number: int,
        platform: str,
        repo_path: str,
        adw_id: str,
        issue_id: int | None,
    ) -> None:
        """Summarise the review with Claude and post it as a PR/MR comment.

        Best-effort: all failures are logged and suppressed so the step does not halt.
        PAT tokens are forwarded following the project convention (GITHUB_PAT → GH_TOKEN,
        GITLAB_PAT → GITLAB_TOKEN).

        Args:
            review_text: Full CodeRabbit review text to summarise.
            pr_number: PR or MR number to comment on.
            platform: ``"github"`` or ``"gitlab"`` (from DEV_SEC_OPS_PLATFORM).
            repo_path: Repository root path for CLI invocations.
            adw_id: ADW ID for the Claude request.
            issue_id: Optional Rouge issue ID for the Claude request.
        """
        func_logger = get_logger(adw_id)
        platform_lower = platform.strip().lower()
        if platform_lower not in {"github", "gitlab"}:
            func_logger.warning(
                "Unsupported DEV_SEC_OPS_PLATFORM value: %s, skipping PR comment", platform
            )
            return

        # Phase 1: generate summary via Claude (execute_template calls into
        # Claude CLI and Supabase; its exception surface is unbounded, so this
        # is treated as an external boundary and caught broadly).
        try:
            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_PLANNER,
                prompt_id=PromptId.CODE_REVIEW_SUMMARY,
                args=[review_text],
                adw_id=adw_id,
                issue_id=issue_id,
                model="sonnet",
                json_schema=CODE_REVIEW_SUMMARY_JSON_SCHEMA,
            )
            summary_response = execute_template(request, require_json=True)
        except Exception as e:
            func_logger.error(
                "Failed to call %s template: %s",
                PromptId.CODE_REVIEW_SUMMARY.value,
                e,
                exc_info=True,
            )
            return

        if not summary_response.success or not summary_response.output:
            func_logger.warning("Failed to generate review summary, skipping PR comment")
            return

        # Parse JSON output to extract summary field
        try:
            parsed_output = json.loads(summary_response.output)
            summary = parsed_output.get("summary", "").strip()
            if not summary:
                func_logger.warning("Empty summary field in JSON response, skipping PR comment")
                return
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            func_logger.error("Failed to parse summary JSON response: %s", e, exc_info=True)
            return
        body = (
            f"{summary}\n\n<details><summary>Full review</summary>" f"\n\n{review_text}\n</details>"
        )
        self._post_comment_to_pr(
            body=body,
            pr_number=pr_number,
            platform_lower=platform_lower,
            repo_path=repo_path,
            adw_id=adw_id,
        )

    def _post_comment_to_pr(
        self,
        body: str,
        pr_number: int,
        platform_lower: str,
        repo_path: str,
        adw_id: str,
    ) -> None:
        """Post a pre-formatted comment to a GitHub PR or GitLab MR via CLI.

        Best-effort: failures are logged and suppressed. PAT tokens are forwarded
        following the project convention (GITHUB_PAT → GH_TOKEN, GITLAB_PAT → GITLAB_TOKEN).
        The caller is responsible for validating that ``platform_lower`` is a supported value.

        Args:
            body: Comment body text to post.
            pr_number: PR or MR number to comment on (caller has already validated > 0).
            platform_lower: Normalised platform string (``"github"`` or ``"gitlab"``).
            repo_path: Repository root path for CLI invocation.
            adw_id: ADW ID for logger retrieval.
        """
        func_logger = get_logger(adw_id)
        if not repo_path.strip():
            func_logger.warning("Empty repo_path, skipping PR comment")
            return

        if not body.strip():
            func_logger.warning("Empty body, skipping PR comment")
            return

        env = os.environ.copy()
        if platform_lower == "github":
            github_pat = os.environ.get("GITHUB_PAT")
            if github_pat:
                env["GH_TOKEN"] = github_pat
            cmd = ["gh", "pr", "comment", str(pr_number), "--body", body]
            label = f"PR #{pr_number}"
        else:
            gitlab_pat = os.environ.get("GITLAB_PAT")
            if gitlab_pat:
                env["GITLAB_TOKEN"] = gitlab_pat
            cmd = ["glab", "mr", "comment", str(pr_number), "--message", body]
            label = f"MR #{pr_number}"

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                timeout=30,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            OSError,
            subprocess.SubprocessError,
        ) as e:
            func_logger.error("Failed to post PR comment via CLI: %s", e, exc_info=True)
            return

        if result.returncode != 0:
            func_logger.error(
                "Failed to post review summary to %s (repo=%s): exit=%s\nstdout: %s\nstderr: %s",
                label,
                repo_path,
                result.returncode,
                result.stdout,
                result.stderr,
            )
        else:
            func_logger.info("Posted review summary to %s", label)

    def run(self, context: WorkflowContext) -> StepResult:
        """Generate review and store result in context.

        Args:
            context: Workflow context with plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load plan data from PlanArtifact (codereview now always has an issue)
        try:
            plan_data = context.load_required_artifact(
                "plan_data",
                "plan",
                PlanArtifact,
                lambda a: a.plan_data,
            )
        except StepInputError as e:
            logger.warning("No plan data available: %s", e)
            return StepResult.fail(f"No plan data available: {e}")

        repo_path = context.repo_paths[0]

        # For codereview/patch workflows, prefer repos where the branch was
        # actually checked out (stored in GitCheckoutArtifact). Fall back to
        # repo_paths[0] when the artifact is absent (e.g. main workflow).
        checkout_artifact = context.load_optional_artifact(
            "git_checkout",
            "git-checkout",
            GitCheckoutArtifact,
            lambda a: a,
        )
        if checkout_artifact is not None and checkout_artifact.checked_out_repos:
            repo_path = checkout_artifact.checked_out_repos[0]
            logger.debug("Using checked-out repo from GitCheckoutArtifact: %s", repo_path)

        # Only codereview workflows should pass a base commit to CodeRabbit.
        # Main/patch workflows use plan_data.plan for markdown content, not a git SHA.
        base_commit = None
        if context.data.get("workflow_type") == "codereview":
            base_commit = context.data.get("base_commit")
            if not base_commit and plan_data.plan:
                base_commit = plan_data.plan

        review_result = self._generate_review(repo_path, context.adw_id, base_commit=base_commit)

        if not review_result.success:
            logger.error("Failed to generate CodeRabbit review: %s", review_result.error)
            return StepResult.fail(f"Failed to generate CodeRabbit review: {review_result.error}")

        if review_result.data is None:
            logger.warning("CodeRabbit review succeeded but no data was returned")
            return StepResult.fail("CodeRabbit review succeeded but no data was returned")

        logger.info("CodeRabbit review generated successfully")

        # Detect whether the review is clean (no actionable issues)
        is_clean = is_clean_review(review_result.data.review_text)
        if is_clean:
            logger.info("Review is clean — no actionable issues detected")
        else:
            logger.info("Review contains issues that need to be addressed")

        # Save artifact
        artifact = CodeReviewArtifact(
            workflow_id=context.adw_id,
            review_data=review_result.data,
            is_clean=is_clean,
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved review artifact for workflow %s", context.adw_id)

        status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
        log_artifact_comment_status(status, msg)

        # Post review summary to PR/MR if pr_number is available
        pr_number = context.data.get("pr_number")
        platform = os.environ.get("DEV_SEC_OPS_PLATFORM")

        if isinstance(pr_number, int) and pr_number > 0 and platform:
            self._post_review_summary_to_pr(
                review_text=review_result.data.review_text,
                pr_number=pr_number,
                platform=platform,
                repo_path=repo_path,
                adw_id=context.adw_id,
                issue_id=context.issue_id,
            )

        # Insert progress comment - best-effort, non-blocking
        if context.issue_id is not None:
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text="CodeRabbit review complete.",
                raw={"text": "CodeRabbit review complete."},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            elif status == "skipped":
                logger.debug(msg)
            else:
                logger.error(msg)

        return StepResult.ok(None)
