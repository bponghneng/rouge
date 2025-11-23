"""Main workflow orchestration runner."""

from logging import Logger

from cape.core.database import fetch_issue
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment
from cape.core.workflow.classify import classify_issue
from cape.core.workflow.implement import implement_plan, parse_implement_output
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.review import generate_review, notify_review_template
from cape.core.workflow.shared import derive_paths_from_plan, get_repo_path, get_working_dir
from cape.core.workflow.status import update_status


def execute_workflow(
    issue_id: int,
    adw_id: str,
    logger: Logger,
) -> bool:
    """Execute complete workflow for an issue.

    This is the main orchestration function that runs all workflow steps:
    1. Fetch issue from database
    2. Classify the issue
    3. Build implementation plan
    4. Find plan file
    5. Implement the plan
    6. Generate CodeRabbit review (new)
    7. Notify review template (new)

    Progress comments are inserted at key points (best-effort, non-blocking).

    Args:
        issue_id: The Cape issue ID to process
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if workflow completed successfully, False otherwise
    """
    logger.info(f"ADW ID: {adw_id}")
    logger.info(f"Processing issue ID: {issue_id}")

    # Fetch issue from Supabase
    logger.info("\n=== Fetching issue from Supabase ===")
    try:
        issue = fetch_issue(issue_id)
        logger.info(f"Issue fetched: ID={issue.id}, Status={issue.status}")
    except ValueError as e:
        logger.error(f"Error fetching issue: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error fetching issue: {e}")
        return False

    # Update status to "started" - best-effort, non-blocking
    update_status(issue_id, "started", logger)

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Workflow started - Issue fetched and validated",
        raw={},
        source="system",
        type="workflow"
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Classify the issue
    logger.info("\n=== Classifying issue ===")
    issue_command, classification_data, error = classify_issue(issue, adw_id, logger)
    if error:
        logger.error(f"Error classifying issue: {error}")
        return False
    if issue_command is None:
        logger.error("Classifier did not return a command")
        return False

    if classification_data:
        logger.info(
            "Issue classified as %s (%s) -> %s",
            classification_data["type"],
            classification_data["level"],
            issue_command,
        )
    else:
        logger.info(f"Issue classified as: {issue_command}")

    # Insert progress comment - best-effort, non-blocking
    if classification_data:
        comment_text = (
            f"Issue classified as {classification_data['type']} "
            f"({classification_data['level']}) -> {issue_command}"
        )
    else:
        comment_text = f"Issue classified as {issue_command}"
    comment = CapeComment(
        issue_id=issue_id,
        comment=comment_text,
        raw={},
        source="system",
        type="workflow"
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Build the implementation plan
    logger.info("\n=== Building implementation plan ===")
    plan_response = build_plan(issue, issue_command, adw_id, logger)
    if not plan_response.success:
        logger.error(f"Error building plan: {plan_response.output}")
        return False
    logger.info(" Implementation plan created")

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Implementation plan created successfully",
        raw={},
        source="system",
        type="workflow"
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Get the path to the plan file that was created
    logger.info("\n=== Finding plan file ===")
    plan_file_path, error = get_plan_file(plan_response.output, issue_id, adw_id, logger)
    if error:
        logger.error(f"Error finding plan file: {error}")
        return False
    if plan_file_path is None:
        logger.error("Plan file path missing despite successful response")
        return False
    logger.info(f"Plan file created: {plan_file_path}")

    # Implement the plan
    logger.info("\n=== Implementing solution ===")
    implement_response = implement_plan(plan_file_path, issue_id, adw_id, logger)
    if not implement_response.success:
        logger.error(f"Error implementing solution: {implement_response.output}")
        return False
    logger.info(" Solution implemented")

    # Parse implementation output to extract metadata
    logger.info("\n=== Parsing implementation output ===")
    parsed_metadata = parse_implement_output(implement_response.output, logger)

    if parsed_metadata:
        logger.info(f"Implementation metadata extracted: {parsed_metadata.get('summary', 'No summary')}")
        logger.debug(f"Files modified: {parsed_metadata.get('files_modified', [])}")

        # Derive paths from the plan file
        paths = derive_paths_from_plan(parsed_metadata.get("path", plan_file_path))
        review_file = paths["review_file"]

        # Generate CodeRabbit review
        logger.info("\n=== Generating CodeRabbit review ===")
        working_dir = get_working_dir()
        repo_path = get_repo_path()

        review_success, review_text = generate_review(
            review_file,
            working_dir,
            repo_path,
            issue_id,
            logger
        )

        if not review_success:
            logger.error("Failed to generate CodeRabbit review")
            # Continue workflow even if review fails - it's optional
        else:
            logger.info(f"CodeRabbit review generated successfully at {review_file}")

            # Notify the /address-review-issues template
            logger.info("\n=== Notifying review template ===")
            notify_success = notify_review_template(
                review_file,
                issue_id,
                adw_id,
                logger
            )

            if not notify_success:
                logger.error("Failed to notify review template")
                # Continue workflow even if notification fails
            else:
                logger.info("Review template notified successfully")
    else:
        logger.warning("Could not parse implementation output, skipping review generation")

    # Update status to "completed" - best-effort, non-blocking
    update_status(issue_id, "completed", logger)

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Solution implemented successfully",
        raw={},
        source="system",
        type="workflow"
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    logger.info("\n=== Workflow completed successfully ===")
    return True