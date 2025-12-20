"""Review generation functionality for workflow orchestration."""

import logging
import os
import subprocess

from rouge.core.models import Comment
from rouge.core.notifications import insert_progress_comment
from rouge.core.workflow.types import ReviewData, StepResult

logger = logging.getLogger(__name__)


def generate_review(
    review_file: str, working_dir: str, repo_path: str, issue_id: int
) -> StepResult[ReviewData]:
    """Generate CodeRabbit review and save to file.

    Args:
        review_file: Path where review should be saved
        working_dir: Working directory for CodeRabbit command
        repo_path: Repository root path
        issue_id: Rouge issue ID for tracking

    Returns:
        StepResult with ReviewData containing review text and file path
    """
    try:
        # Ensure specs directory exists
        review_dir = os.path.dirname(review_file)
        if review_dir:
            os.makedirs(review_dir, exist_ok=True)

        # Build absolute config path and validate it exists
        config_path = os.path.join(working_dir, ".coderabbit.yaml")
        if not os.path.exists(config_path):
            return StepResult.fail(f"CodeRabbit config not found at {config_path}")
        logger.debug(f"Using CodeRabbit config at {config_path}")

        # Build CodeRabbit command
        # Note: Uses direct 'coderabbit --prompt-only' instead of 'coderabbit review --prompt-only'
        # This change was made to align with the updated CodeRabbit CLI interface
        cmd = [
            "coderabbit",
            "--prompt-only",
            "--config",
            config_path,
        ]

        logger.debug(f"Executing CodeRabbit command: {' '.join(cmd)}")
        logger.debug(f"Running from directory: {repo_path}")

        # Execute CodeRabbit review from repo_path
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"CodeRabbit review failed with code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            return StepResult.fail(f"CodeRabbit review failed with code {result.returncode}")

        # Write review to file
        with open(review_file, "w") as f:
            f.write(result.stdout)

        logger.info(f"CodeRabbit review generated ({len(result.stdout)} chars)")
        logger.debug(f"Review written to {review_file}")

        # Read back the content
        with open(review_file, "r") as f:
            review_text = f.read()

        # Insert progress comment with artifact
        comment = Comment(
            issue_id=issue_id,
            comment=f"CodeRabbit review generated at {review_file}",
            raw={
                "review_file": review_file,
                "review_text": review_text[:500],
            },  # First 500 chars for preview
            source="system",
            type="artifact",
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert review artifact comment: {msg}")
        else:
            logger.debug(f"Review artifact comment inserted: {msg}")

        return StepResult.ok(ReviewData(review_text=review_text, review_file=review_file))

    except subprocess.TimeoutExpired:
        logger.error("CodeRabbit review timed out after 300 seconds")
        return StepResult.fail("CodeRabbit review timed out after 300 seconds")
    except Exception as e:
        logger.error(f"Failed to generate review: {e}")
        return StepResult.fail(f"Failed to generate review: {e}")
