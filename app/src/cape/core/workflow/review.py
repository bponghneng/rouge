"""Review generation and notification functionality for workflow orchestration."""

import os
import subprocess
from logging import Logger
from typing import Optional, Tuple

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment
from cape.core.workflow.shared import AGENT_IMPLEMENTOR


def generate_review(
    review_file: str,
    working_dir: str,
    repo_path: str,
    issue_id: int,
    logger: Logger
) -> Tuple[bool, Optional[str]]:
    """Generate CodeRabbit review and save to file.

    Args:
        review_file: Path where review should be saved
        working_dir: Working directory for CodeRabbit command
        repo_path: Repository root path
        issue_id: Cape issue ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (success, review_text) where review_text is None on failure
    """
    try:
        # Ensure specs directory exists
        review_dir = os.path.dirname(review_file)
        if review_dir:
            os.makedirs(review_dir, exist_ok=True)

        # Build CodeRabbit command
        cmd = [
            "coderabbit",
            "review",
            "--cwd", working_dir,
            "--config", f"{working_dir}/.coderabbit.yaml",
            "--prompt-only"
        ]

        logger.debug(f"Executing CodeRabbit command: {' '.join(cmd)}")

        # Execute CodeRabbit review
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            logger.error(f"CodeRabbit review failed with code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            return False, None

        # Write review to file
        with open(review_file, 'w') as f:
            f.write(result.stdout)

        logger.debug(f"Review written to {review_file}")

        # Read back the content
        with open(review_file, 'r') as f:
            review_text = f.read()

        # Insert progress comment with artifact
        comment = CapeComment(
            issue_id=issue_id,
            comment=f"CodeRabbit review generated at {review_file}",
            raw={"review_file": review_file, "review_text": review_text[:500]},  # First 500 chars for preview
            source="system",
            type="artifact"
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert review artifact comment: {msg}")
        else:
            logger.debug(f"Review artifact comment inserted: {msg}")

        return True, review_text

    except subprocess.TimeoutExpired:
        logger.error("CodeRabbit review timed out after 300 seconds")
        return False, None
    except Exception as e:
        logger.error(f"Failed to generate review: {e}")
        return False, None


def notify_review_template(
    review_file: str,
    issue_id: int,
    adw_id: str,
    logger: Logger
) -> bool:
    """Notify the /address-review-issues template with the review file.

    Args:
        review_file: Path to the review file
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True on success, False on failure
    """
    try:
        # Validate review file exists
        if not os.path.exists(review_file):
            logger.error(f"Review file does not exist: {review_file}")
            return False

        logger.debug(f"Invoking /address-review-issues template with review file: {review_file}")

        # Call execute_template with the review file
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_IMPLEMENTOR,
            slash_command="/address-review-issues",
            args=[review_file],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
        )

        logger.debug(
            "notify_review_template request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        response = execute_template(request)

        logger.debug(
            "notify_review_template response: success=%s",
            response.success,
        )

        if not response.success:
            logger.error(f"Failed to execute /address-review-issues template: {response.output}")
            return False

        # Insert progress comment with template output
        comment = CapeComment(
            issue_id=issue_id,
            comment="Review issues template executed successfully",
            raw={"template_output": response.output[:1000]},  # First 1000 chars of output
            source="system",
            type="artifact"
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert template notification comment: {msg}")
        else:
            logger.debug(f"Template notification comment inserted: {msg}")

        return True

    except Exception as e:
        logger.error(f"Failed to notify review template: {e}")
        return False