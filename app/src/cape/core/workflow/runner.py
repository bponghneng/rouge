"""Main workflow orchestration runner."""

from logging import Logger

from cape.core.database import fetch_issue
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment, make_progress_comment_handler
from cape.core.workflow.acceptance import notify_plan_acceptance
from cape.core.workflow.address_review import address_review_issues
from cape.core.workflow.classify import classify_issue
from cape.core.workflow.implement import implement_plan, parse_implement_output
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.review import generate_review
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
        comment="Workflow started. Issue fetched and validated",
        raw={
            "issue_id": issue_id,
            "text": "Workflow started. Issue fetched and validated.",
        },
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Classify the issue
    logger.info("\n=== Classifying issue ===")
    classify_handler = make_progress_comment_handler(issue.id, adw_id, logger)
    result = classify_issue(issue, adw_id, logger, stream_handler=classify_handler)
    if not result.success:
        logger.error(f"Error classifying issue: {result.error}")
        return False
    if result.data is None:
        logger.error("Classifier did not return data")
        return False

    issue_command = result.data.command
    classification_data = result.data.classification

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
        issue_id=issue_id, comment=comment_text, raw=classification_data, source="system", type="workflow"
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Build the implementation plan
    logger.info("\n=== Building implementation plan ===")
    plan_handler = make_progress_comment_handler(issue.id, adw_id, logger)
    plan_response = build_plan(issue, issue_command, adw_id, logger, stream_handler=plan_handler)
    if not plan_response.success:
        logger.error(f"Error building plan: {plan_response.error}")
        return False
    logger.info(f"Implementation plan created:\n\n{plan_response}")

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Implementation plan created successfully",
        raw={},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Get the path to the plan file that was created
    logger.info("\n=== Finding plan file ===")
    if plan_response.data is None:
        logger.error("Plan data missing despite successful response")
        return False
    plan_file_result = get_plan_file(plan_response.data.output, issue_id, adw_id, logger)
    if not plan_file_result.success:
        logger.error(f"Error finding plan file: {plan_file_result.error}")
        return False
    if plan_file_result.data is None:
        logger.error("Plan file data missing despite successful response")
        return False
    plan_file_path = plan_file_result.data.file_path
    logger.info(f"Plan file created: {plan_file_path}")

    # Implement the plan
    logger.info("\n=== Implementing solution ===")
    implement_response = implement_plan(plan_file_path, issue_id, adw_id, logger)
    if not implement_response.success:
        logger.error(f"Error implementing solution: {implement_response.error}")
        return False
    logger.info(" Solution implemented")

    # Log implementation output (deprecated parsing function)
    logger.info("\n=== Logging implementation output ===")
    if implement_response.data is None:
        logger.error("Implementation data missing despite successful response")
        return False
    parse_implement_output(implement_response.data.output, logger)

    # Find the plan file that was implemented
    logger.info("\n=== Finding implemented plan file ===")
    impl_plan_result = get_plan_file(implement_response.data.output, issue_id, adw_id, logger)
    if not impl_plan_result.success:
        logger.error(f"Error finding implemented plan file: {impl_plan_result.error}")
        # Fall back to the original plan file path
        logger.warning(f"Falling back to original plan file: {plan_file_path}")
        implemented_plan_path = plan_file_path
    elif impl_plan_result.data is None:
        logger.warning("Could not determine implemented plan file, using original")
        implemented_plan_path = plan_file_path
    else:
        implemented_plan_path = impl_plan_result.data.file_path
        logger.info(f"Implemented plan file: {implemented_plan_path}")

    # Derive paths from the implemented plan file
    paths = derive_paths_from_plan(implemented_plan_path)
    review_file = paths["review_file"]

    # Generate CodeRabbit review
    logger.info("\n=== Generating CodeRabbit review ===")
    working_dir = get_working_dir()
    repo_path = get_repo_path()

    review_result = generate_review(review_file, working_dir, repo_path, issue_id, logger)

    if not review_result.success:
        logger.error(f"Failed to generate CodeRabbit review: {review_result.error}")
        # Continue workflow even if review fails - it's optional
    else:
        if review_result.data is None:
            logger.warning("CodeRabbit review succeeded but no data/review_file was returned")
        else:
            logger.info(
                f"CodeRabbit review generated successfully at {review_result.data.review_file}"
            )

            # Notify the /address-review-issues template
            logger.info("\n=== Notifying review template ===")
            review_handler = make_progress_comment_handler(issue_id, adw_id, logger)
            review_issues_result = address_review_issues(
                review_file, issue_id, adw_id, logger, stream_handler=review_handler
            )

            if not review_issues_result.success:
                logger.error(f"Failed to notify review template: {review_issues_result.error}")
                # Continue workflow even if notification fails
            else:
                logger.info("Review template notified successfully")

    # Validate plan acceptance
    logger.info("\n=== Validating plan acceptance ===")
    acceptance_handler = make_progress_comment_handler(issue_id, adw_id, logger)
    acceptance_result = notify_plan_acceptance(
        implemented_plan_path, issue_id, adw_id, logger, stream_handler=acceptance_handler
    )

    if not acceptance_result.success:
        logger.error(f"Failed to validate plan acceptance: {acceptance_result.error}")
        # Continue workflow even if acceptance validation fails
    else:
        logger.info("Plan acceptance validated successfully")

    # Update status to "completed" - best-effort, non-blocking
    update_status(issue_id, "completed", logger)

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Solution implemented successfully",
        raw={},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    logger.info("\n=== Workflow completed successfully ===")
    return True
