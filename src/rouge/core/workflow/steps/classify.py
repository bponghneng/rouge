"""Classify issue step implementation."""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import ClassificationArtifact, IssueArtifact
from rouge.core.workflow.classify import classify_issue
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


class ClassifyStep(WorkflowStep):
    """Classify issue and determine workflow command."""

    @property
    def name(self) -> str:
        return "Classifying issue"

    def run(self, context: WorkflowContext) -> StepResult:
        """Classify the issue and store classification data.

        Args:
            context: Workflow context with issue to classify

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load issue from artifact if not in context
        issue = context.load_issue_artifact_if_missing(IssueArtifact, lambda a: a.issue)

        if issue is None:
            logger.error("Cannot classify: issue not fetched")
            return StepResult.fail("Cannot classify: issue not fetched")

        classify_handler = make_progress_comment_handler(issue.id, context.adw_id)
        result = classify_issue(issue, context.adw_id, stream_handler=classify_handler)

        if not result.success:
            logger.error("Error classifying issue: %s", result.error)
            return StepResult.fail(f"Error classifying issue: {result.error}")

        if result.data is None:
            logger.error("Classifier did not return data")
            return StepResult.fail("Classifier did not return data")

        # Store classification data in context
        context.data["classify_data"] = result.data

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ClassificationArtifact(
                workflow_id=context.adw_id,
                classify_data=result.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved classification artifact for workflow %s", context.adw_id)

        issue_command = result.data.command
        classification_data = result.data.classification

        if classification_data:
            logger.info(
                "Issue classified as %s (%s) -> %s",
                classification_data["type"],
                classification_data["level"],
                issue_command,
            )
            comment_text = (
                f"Issue classified as {classification_data['type']} "
                f"({classification_data['level']}) -> {issue_command}"
            )
        else:
            logger.info("Issue classified as: %s", issue_command)
            comment_text = f"Issue classified as {issue_command}"

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=issue.id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={"text": comment_text},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
