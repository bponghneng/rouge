"""Review generation functionality for workflow orchestration."""

import logging
import os
import subprocess

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.types import ReviewData, StepResult

logger = logging.getLogger(__name__)


def generate_review(
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
        # Build absolute config path and validate it exists (config must be in repo root)
        config_path = os.path.join(repo_path, ".coderabbit.yaml")
        if not os.path.exists(config_path):
            return StepResult.fail(f"CodeRabbit config not found at {config_path}")
        logger.debug("Using CodeRabbit config at %s", config_path)

        # Build CodeRabbit command
        # Note: Uses direct 'coderabbit --prompt-only' instead of 'coderabbit review --prompt-only'
        # This change was made to align with the updated CodeRabbit CLI interface
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
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=300)

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
        logger.exception("CodeRabbit review timed out after 300 seconds")
        return StepResult.fail("CodeRabbit review timed out after 300 seconds")
    except Exception as e:
        logger.exception("Failed to generate review")
        return StepResult.fail(f"Failed to generate review: {e}")
