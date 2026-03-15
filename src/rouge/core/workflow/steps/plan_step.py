"""Plan building step implementation."""

from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ClassifyArtifact,
    FetchIssueArtifact,
    PlanArtifact,
)
from rouge.core.workflow.plan_common import build_plan_from_template
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ClassifyData, PlanData, StepResult


class PlanStep(WorkflowStep):
    """Plan building step implementation."""

    @property
    def name(self) -> str:
        return "Building implementation plan"

    def _build_plan(
        self,
        issue: Issue,
        prompt_id: PromptId,
        adw_id: str,
    ) -> StepResult[PlanData]:
        """Build implementation plan for the issue using the specified prompt.

        Args:
            issue: The Rouge issue to plan for
            prompt_id: The planning prompt to use (e.g., PromptId.FEATURE_PLAN)
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with PlanData containing output and optional session_id
        """
        return build_plan_from_template(issue, prompt_id, adw_id)

    def run(self, context: WorkflowContext) -> StepResult:
        """Build implementation plan and store in context.

        Args:
            context: Workflow context with classify_data

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load issue from artifact (required)
        try:
            issue = context.load_required_artifact(
                "issue", "fetch-issue", FetchIssueArtifact, lambda a: a.issue
            )
        except StepInputError as e:
            logger.error("Cannot build plan: issue not fetched: %s", e)
            return StepResult.fail(f"Cannot build plan: issue not fetched: {e}")

        # Load classification from artifact (required)
        try:
            classify_data: ClassifyData = context.load_required_artifact(
                "classify_data",
                "classify",
                ClassifyArtifact,
                lambda a: a.classify_data,
            )
        except StepInputError as e:
            logger.error("Cannot build plan: classify_data not available: %s", e)
            return StepResult.fail(f"Cannot build plan: classify_data not available: {e}")

        plan_response = self._build_plan(
            issue,
            classify_data.command,  # already a PromptId
            context.adw_id,
        )

        if not plan_response.success:
            logger.error("Error building plan: %s", plan_response.error)
            return StepResult.fail(f"Error building plan: {plan_response.error}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        # Save artifact
        if plan_response.data is not None:
            artifact = PlanArtifact(
                workflow_id=context.adw_id,
                plan_data=plan_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved plan artifact for workflow %s", context.adw_id)

            status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
            log_artifact_comment_status(status, msg)

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
            raw={"text": comment_text, "parsed": parsed_data},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
