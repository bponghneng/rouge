"""Review generation step implementation."""

import logging
import os
import subprocess

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import PlanArtifact, ReviewArtifact
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ReviewData, StepResult

logger = logging.getLogger(__name__)

# Module-level constant for step name used in rerun_from references
CODE_REVIEW_STEP_NAME = "Generating CodeRabbit review"


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

    def _parse_timeout_seconds(self) -> int:
        """Parse CODERABBIT_TIMEOUT_SECONDS from environment with safe fallback.

        Returns:
            Timeout in seconds, defaulting to 600 (10 minutes) if env var is
            missing or malformed.
        """
        try:
            return int(os.getenv("CODERABBIT_TIMEOUT_SECONDS", "600"))
        except (ValueError, TypeError):
            logger.warning("Invalid CODERABBIT_TIMEOUT_SECONDS value, using default 600 seconds")
            return 600

    def _generate_review(
        self,
        repo_path: str,
        issue_id: int | None,
        adw_id: str | None = None,
        base_commit: str | None = None,
    ) -> StepResult[ReviewData]:
        """Generate CodeRabbit review output.

        Args:
            repo_path: Repository root path where .coderabbit.yaml config is located
            issue_id: Optional Rouge issue ID for tracking (None for standalone review)
            adw_id: Optional ADW ID for associating comment with workflow
            base_commit: Optional base commit SHA for CodeRabbit --base-commit flag

        Returns:
            StepResult with ReviewData containing review text
        """
        try:
            # Read timeout from environment variable with default of 600 seconds (10 minutes)
            timeout_seconds = self._parse_timeout_seconds()

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

            # Emit comment with full review text (logs to console for standalone workflows)
            payload = CommentPayload(
                issue_id=issue_id,
                adw_id=adw_id,
                text="CodeRabbit review generated",
                raw={
                    "review_text": review_text,
                },
                source="system",
                kind="artifact",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug("Review artifact comment inserted: %s", msg)
            elif status == "skipped":
                logger.debug(msg)
            else:
                logger.error("Failed to insert review artifact comment: %s", msg)

            return StepResult.ok(ReviewData(review_text=review_text))

        except subprocess.TimeoutExpired:
            timeout_seconds = self._parse_timeout_seconds()
            logger.exception("CodeRabbit review timed out after %s seconds", timeout_seconds)
            return StepResult.fail(f"CodeRabbit review timed out after {timeout_seconds} seconds")
        except Exception as e:
            logger.exception("Failed to generate review")
            return StepResult.fail(f"Failed to generate review: {e}")

    def run(self, context: WorkflowContext) -> StepResult:
        """Generate review and store result in context.

        Args:
            context: Workflow context with optional plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # For issue-based workflows, we expect plan data for context
        # For standalone codereview workflows (issue_id=None), plan is not required
        if context.issue_id is not None:
            plan_data = context.load_artifact_if_missing(
                "plan_data",
                "plan",
                PlanArtifact,
                lambda a: a.plan_data,
            )

            if plan_data is None:
                logger.warning("No plan data available for issue-based workflow")
                return StepResult.fail("No plan data available for issue-based workflow")
        else:
            # Standalone codereview workflow - no plan needed
            logger.debug("Codereview workflow without issue - proceeding without plan data")

        repo_path = get_repo_path()

        base_commit = context.data.get("base_commit")

        review_result = self._generate_review(
            repo_path, context.issue_id, context.adw_id, base_commit=base_commit
        )

        if not review_result.success:
            logger.error("Failed to generate CodeRabbit review: %s", review_result.error)
            return StepResult.fail(f"Failed to generate CodeRabbit review: {review_result.error}")

        if review_result.data is None:
            logger.warning("CodeRabbit review succeeded but no data was returned")
            return StepResult.fail("CodeRabbit review succeeded but no data was returned")

        logger.info("CodeRabbit review generated successfully")

        # Store review data in context
        context.data["review_data"] = review_result.data

        # Detect whether the review is clean (no actionable issues)
        is_clean = is_clean_review(review_result.data.review_text)
        context.data["review_is_clean"] = is_clean
        if is_clean:
            logger.info("Review is clean — no actionable issues detected")
        else:
            logger.info("Review contains issues that need to be addressed")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ReviewArtifact(
                workflow_id=context.adw_id,
                review_data=review_result.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review artifact for workflow %s", context.adw_id)

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
