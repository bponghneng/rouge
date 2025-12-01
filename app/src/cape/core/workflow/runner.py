"""Main workflow orchestration runner."""

from logging import Logger
from typing import Optional, Tuple

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.database import fetch_issue
from cape.core.models import CapeComment, CapeIssue
from cape.core.notifications import insert_progress_comment, make_progress_comment_handler
from cape.core.workflow.acceptance import notify_plan_acceptance
from cape.core.workflow.address_review import address_review_issues
from cape.core.workflow.classify import classify_issue
from cape.core.workflow.implement import implement_plan
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.review import generate_review
from cape.core.workflow.shared import (
    AGENT_IMPLEMENTOR,
    derive_paths_from_plan,
    get_repo_path,
    get_working_dir,
)
from cape.core.workflow.status import update_status
from cape.core.workflow.types import (
    ClassifyData,
    ClassifySlashCommand,
    ImplementData,
    PlanData,
    ReviewData,
)


def _fetch_issue(issue_id: int, logger: Logger) -> Tuple[Optional[CapeIssue], bool]:
    """Fetch and validate issue from Supabase.

    Args:
        issue_id: The Cape issue ID to fetch
        logger: Logger instance

    Returns:
        Tuple of (issue or None, success boolean)
    """
    logger.info("\n=== Fetching issue from Supabase ===")
    try:
        issue = fetch_issue(issue_id)
        logger.info(f"Issue fetched: ID={issue.id}, Status={issue.status}")
        return issue, True
    except ValueError as e:
        logger.error(f"Error fetching issue: {e}")
        return None, False
    except Exception as e:
        logger.error(f"Unexpected error fetching issue: {e}")
        return None, False


def _classify_issue(
    issue: CapeIssue, adw_id: str, logger: Logger
) -> Tuple[Optional[ClassifyData], bool]:
    """Classify issue and return command and classification data.

    Args:
        issue: The Cape issue to classify
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (ClassifyData or None, success boolean)
    """
    logger.info("\n=== Classifying issue ===")
    classify_handler = make_progress_comment_handler(issue.id, adw_id, logger)
    result = classify_issue(issue, adw_id, logger, stream_handler=classify_handler)
    if not result.success:
        logger.error(f"Error classifying issue: {result.error}")
        return None, False
    if result.data is None:
        logger.error("Classifier did not return data")
        return None, False

    return result.data, True


def _build_plan(
    issue: CapeIssue,
    command: ClassifySlashCommand,
    adw_id: str,
    logger: Logger,
) -> Tuple[Optional[PlanData], bool]:
    """Build implementation plan for the issue.

    Args:
        issue: The Cape issue to plan for
        command: The triage command to use
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (PlanData or None, success boolean)
    """
    logger.info("\n=== Building implementation plan ===")
    plan_handler = make_progress_comment_handler(issue.id, adw_id, logger)
    plan_response = build_plan(issue, command, adw_id, logger, stream_handler=plan_handler)
    if not plan_response.success:
        logger.error(f"Error building plan: {plan_response.error}")
        return None, False
    logger.info(f"Implementation plan created:\n\n{plan_response}")
    return plan_response.data, True


def _find_plan_file(
    plan_output: str, issue_id: int, adw_id: str, logger: Logger
) -> Tuple[Optional[str], bool]:
    """Get plan file path from plan output.

    Args:
        plan_output: The output from the build_plan step
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (file path or None, success boolean)
    """
    logger.info("\n=== Finding plan file ===")
    plan_file_result = get_plan_file(plan_output, issue_id, adw_id, logger)
    if not plan_file_result.success:
        logger.error(f"Error finding plan file: {plan_file_result.error}")
        return None, False
    if plan_file_result.data is None:
        logger.error("Plan file data missing despite successful response")
        return None, False
    plan_file_path = plan_file_result.data.file_path
    logger.info(f"Plan file created: {plan_file_path}")
    return plan_file_path, True


def _implement_plan(
    plan_file: str, issue_id: int, adw_id: str, logger: Logger
) -> Tuple[Optional[ImplementData], bool]:
    """Execute implementation of the plan.

    Args:
        plan_file: Path to the plan file to implement
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (ImplementData or None, success boolean)
    """
    logger.info("\n=== Implementing solution ===")
    implement_response = implement_plan(plan_file, issue_id, adw_id, logger)
    if not implement_response.success:
        logger.error(f"Error implementing solution: {implement_response.error}")
        return None, False
    logger.info(" Solution implemented")
    if implement_response.data is None:
        logger.error("Implementation data missing despite successful response")
        return None, False
    logger.debug("Output preview: %s...", implement_response.data.output[:200])
    return implement_response.data, True


def _find_implemented_plan_file(
    impl_output: str,
    issue_id: int,
    adw_id: str,
    logger: Logger,
    fallback_path: str,
) -> str:
    """Find implemented plan file with fallback to original path.

    Args:
        impl_output: The output from the implementation step
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance
        fallback_path: Path to use if implemented plan file not found

    Returns:
        Path to the implemented plan file
    """
    logger.info("\n=== Finding implemented plan file ===")
    impl_plan_result = get_plan_file(impl_output, issue_id, adw_id, logger)
    if not impl_plan_result.success:
        logger.error(f"Error finding implemented plan file: {impl_plan_result.error}")
        logger.warning(f"Falling back to original plan file: {fallback_path}")
        return fallback_path
    if impl_plan_result.data is None:
        logger.warning("Could not determine implemented plan file, using original")
        return fallback_path
    implemented_plan_path = impl_plan_result.data.file_path
    logger.info(f"Implemented plan file: {implemented_plan_path}")
    return implemented_plan_path


def _generate_review(
    review_file: str,
    working_dir: str,
    repo_path: str,
    issue_id: int,
    logger: Logger,
) -> Tuple[Optional[ReviewData], bool]:
    """Generate CodeRabbit review.

    Args:
        review_file: Path to save the review
        working_dir: Working directory for review
        repo_path: Path to the repository
        issue_id: Cape issue ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (ReviewData or None, success boolean)
    """
    logger.info("\n=== Generating CodeRabbit review ===")
    review_result = generate_review(review_file, working_dir, repo_path, issue_id, logger)

    if not review_result.success:
        logger.error(f"Failed to generate CodeRabbit review: {review_result.error}")
        return None, False

    if review_result.data is None:
        logger.warning("CodeRabbit review succeeded but no data/review_file was returned")
        return None, False

    logger.info(f"CodeRabbit review generated successfully at {review_result.data.review_file}")
    return review_result.data, True


def _address_review(review_file: str, issue_id: int, adw_id: str, logger: Logger) -> bool:
    """Address review issues.

    Args:
        review_file: Path to the review file
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if review issues addressed successfully, False otherwise
    """
    logger.info("\n=== Notifying review template ===")
    review_handler = make_progress_comment_handler(issue_id, adw_id, logger)
    review_issues_result = address_review_issues(
        review_file, issue_id, adw_id, logger, stream_handler=review_handler
    )

    if not review_issues_result.success:
        logger.error(f"Failed to notify review template: {review_issues_result.error}")
        return False

    logger.info("Review template notified successfully")
    return True


def _validate_acceptance(plan_path: str, issue_id: int, adw_id: str, logger: Logger) -> bool:
    """Validate plan acceptance.

    Args:
        plan_path: Path to the plan file to validate
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if validation succeeded, False otherwise
    """
    logger.info("\n=== Validating plan acceptance ===")
    acceptance_handler = make_progress_comment_handler(issue_id, adw_id, logger)
    acceptance_result = notify_plan_acceptance(
        plan_path, issue_id, adw_id, logger, stream_handler=acceptance_handler
    )

    if not acceptance_result.success:
        logger.error(f"Failed to validate plan acceptance: {acceptance_result.error}")
        return False

    logger.info("Plan acceptance validated successfully")
    return True


def _run_code_quality(issue_id: int, adw_id: str, logger: Logger) -> bool:
    """Run code quality checks via /adw-code-quality slash command.

    This is a best-effort step that continues workflow even if it fails.

    Args:
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if code quality checks passed, False otherwise
    """
    logger.info("\n=== Running code quality checks ===")

    try:
        quality_handler = make_progress_comment_handler(issue_id, adw_id, logger)

        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_IMPLEMENTOR,
            slash_command="/adw-code-quality",
            args=[],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
        )

        logger.debug(
            "code_quality request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        response = execute_template(request, stream_handler=quality_handler)

        logger.debug("code_quality response: success=%s", response.success)

        if not response.success:
            logger.warning(f"Code quality checks failed: {response.output}")
            return False

        logger.info("Code quality checks completed successfully")

        # Insert progress comment - best-effort, non-blocking
        comment = CapeComment(
            issue_id=issue_id,
            comment="Code quality checks completed.",
            raw={"text": "Code quality checks completed."},
            source="system",
            type="workflow",
        )
        status, msg = insert_progress_comment(comment)
        logger.debug(msg) if status == "success" else logger.error(msg)

        return True

    except Exception as e:
        logger.warning(f"Code quality step failed: {e}")
        return False


def _prepare_pull_request(issue_id: int, adw_id: str, logger: Logger) -> bool:
    """Prepare pull request via /adw-pull-request slash command.

    This is a best-effort step that continues workflow even if it fails.

    Args:
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if PR preparation succeeded, False otherwise
    """
    logger.info("\n=== Preparing pull request ===")

    try:
        pr_handler = make_progress_comment_handler(issue_id, adw_id, logger)

        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_IMPLEMENTOR,
            slash_command="/adw-pull-request",
            args=[],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
        )

        logger.debug(
            "pull_request request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        response = execute_template(request, stream_handler=pr_handler)

        logger.debug("pull_request response: success=%s", response.success)

        if not response.success:
            logger.warning(f"Pull request preparation failed: {response.output}")
            return False

        logger.info("Pull request prepared successfully")

        # Insert progress comment - best-effort, non-blocking
        comment = CapeComment(
            issue_id=issue_id,
            comment="Pull request prepared.",
            raw={"text": "Pull request prepared."},
            source="system",
            type="workflow",
        )
        status, msg = insert_progress_comment(comment)
        logger.debug(msg) if status == "success" else logger.error(msg)

        return True

    except Exception as e:
        logger.warning(f"Pull request preparation failed: {e}")
        return False


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
    6. Generate CodeRabbit review
    7. Address review issues
    8. Run code quality checks (best-effort)
    9. Validate plan acceptance
    10. Prepare pull request (best-effort)

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

    # Step 1: Fetch issue from Supabase
    issue, success = _fetch_issue(issue_id, logger)
    if not success or issue is None:
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

    # Step 2: Classify the issue
    classify_data, success = _classify_issue(issue, adw_id, logger)
    if not success or classify_data is None:
        return False

    issue_command = classify_data.command
    classification_data = classify_data.classification

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
        raw={"text": comment_text},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Step 3: Build the implementation plan
    plan_data, success = _build_plan(issue, issue_command, adw_id, logger)
    if not success or plan_data is None:
        return False

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Implementation plan created successfully",
        raw={"text": "Implementation plan created successfully."},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Step 4: Get the path to the plan file that was created
    plan_file_path, success = _find_plan_file(plan_data.output, issue_id, adw_id, logger)
    if not success or plan_file_path is None:
        return False

    # Step 5: Implement the plan
    implement_data, success = _implement_plan(plan_file_path, issue_id, adw_id, logger)
    if not success or implement_data is None:
        return False

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Implementation complete.",
        raw={"text": "Implementation complete."},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Find the plan file that was implemented
    implemented_plan_path = _find_implemented_plan_file(
        implement_data.output, issue_id, adw_id, logger, plan_file_path
    )

    # Derive paths from the implemented plan file
    paths = derive_paths_from_plan(implemented_plan_path)
    review_file = paths["review_file"]

    # Step 6: Generate CodeRabbit review
    working_dir = get_working_dir()
    repo_path = get_repo_path()

    review_data, review_success = _generate_review(
        review_file, working_dir, repo_path, issue_id, logger
    )

    if review_success and review_data is not None:
        # Insert progress comment - best-effort, non-blocking
        comment = CapeComment(
            issue_id=issue_id,
            comment="CodeRabbit review complete.",
            raw={"text": "CodeRabbit review complete."},
            source="system",
            type="workflow",
        )
        status, msg = insert_progress_comment(comment)
        logger.debug(msg) if status == "success" else logger.error(msg)

        # Step 7: Address review issues
        _address_review(review_file, issue_id, adw_id, logger)

        # Insert progress comment - best-effort, non-blocking
        comment = CapeComment(
            issue_id=issue_id,
            comment="Review issues addressed.",
            raw={"text": "Review issues addressed."},
            source="system",
            type="workflow",
        )
        status, msg = insert_progress_comment(comment)
        logger.debug(msg) if status == "success" else logger.error(msg)

    # Step 8: Run code quality checks (best-effort, continues on failure)
    _run_code_quality(issue_id, adw_id, logger)

    # Step 9: Validate plan acceptance
    _validate_acceptance(implemented_plan_path, issue_id, adw_id, logger)

    # Insert progress comment with artifact
    comment = CapeComment(
        issue_id=issue_id,
        comment="Plan acceptance validation completed",
        raw={"text": "Plan acceptance validation completed."},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    if status != "success":
        logger.error(f"Failed to insert plan acceptance comment: {msg}")
    else:
        logger.debug(f"Plan acceptance comment inserted: {msg}")

    # Step 10: Prepare pull request (best-effort, continues on failure)
    _prepare_pull_request(issue_id, adw_id, logger)

    # Update status to "completed" - best-effort, non-blocking
    update_status(issue_id, "completed", logger)

    # Insert progress comment - best-effort, non-blocking
    comment = CapeComment(
        issue_id=issue_id,
        comment="Solution implemented successfully",
        raw={"text": "Solution implemented successfully."},
        source="system",
        type="workflow",
    )
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)

    logger.info("\n=== Workflow completed successfully ===")
    return True
