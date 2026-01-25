"""Plan building step implementation."""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import (
    ClassificationArtifact,
    IssueArtifact,
    PlanArtifact,
)
from rouge.core.workflow.plan import build_plan
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ClassifyData, StepResult

logger = logging.getLogger(__name__)


class BuildPlanStep(WorkflowStep):
    """Plan building step implementation."""

    @property
    def name(self) -> str:
        return "Building implementation plan"

    def run(self, context: WorkflowContext) -> StepResult:
        """Build implementation plan and store in context.

        Args:
            context: Workflow context with classify_data

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load issue from artifact if not in context
        issue = context.load_issue_artifact_if_missing(IssueArtifact, lambda a: a.issue)

        if issue is None:
            logger.error("Cannot build plan: issue not fetched")
            return StepResult.fail("Cannot build plan: issue not fetched")

        # Try to load classification from artifact if not in context
        classify_data: ClassifyData | None = context.load_artifact_if_missing(
            "classify_data",
            "classification",
            ClassificationArtifact,
            lambda a: a.classify_data,
        )

        if classify_data is None:
            logger.error("Cannot build plan: classify_data not available")
            return StepResult.fail("Cannot build plan: classify_data not available")

        plan_handler = make_progress_comment_handler(issue.id, context.adw_id)
        plan_response = build_plan(
            issue,
            classify_data.command,
            context.adw_id,
            stream_handler=plan_handler,
        )

        if not plan_response.success:
            logger.error("Error building plan: %s", plan_response.error)
            return StepResult.fail(f"Error building plan: {plan_response.error}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        # Save artifact if artifact store is available
        if (
            context.artifacts_enabled
            and context.artifact_store is not None
            and plan_response.data is not None
        ):
            artifact = PlanArtifact(
                workflow_id=context.adw_id,
                plan_data=plan_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved plan artifact for workflow %s", context.adw_id)

        # Build progress comment from parsed plan data
        parsed_data = plan_response.metadata.get("parsed_data", {})
        # Extract title from one of: chore, bug, feature keys
        title = (
            parsed_data.get("chore")
            or parsed_data.get("bug")
            or parsed_data.get("feature")
            or "Implementation plan created"
        )
        summary = parsed_data.get("summary", "")
        comment_text = f"{title}\n\n{summary}" if summary else title

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=issue.id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={"text": parsed_data},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
