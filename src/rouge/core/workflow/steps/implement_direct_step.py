"""Direct implementation step (no plan artifact)."""

from pydantic import ValidationError

from rouge.core.agent import execute_prompt_raw
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    FetchIssueArtifact,
    ImplementArtifact,
)
from rouge.core.workflow.shared import AGENT_PLAN_IMPLEMENTOR
from rouge.core.workflow.status import update_status
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.steps.implement_step import (
    IMPLEMENT_JSON_SCHEMA,
    IMPLEMENT_REQUIRED_FIELDS,
)
from rouge.core.workflow.types import ImplementData, RepoChangeDetail, StepResult


class ImplementDirectStep(WorkflowStep):
    """Execute direct implementation from issue description (no plan)."""

    @property
    def name(self) -> str:
        return "Implementing direct solution"

    @property
    def is_critical(self) -> bool:
        return True

    def _implement_direct(
        self, issue_description: str, issue_id: int, adw_id: str
    ) -> StepResult[ImplementData]:
        """Implement directly from issue description using Claude Code template.

        Uses the implement-direct prompt template via execute_template pattern.

        Args:
            issue_description: The issue description to implement from
            issue_id: Issue ID for tracking
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with ImplementData containing output and optional session_id
        """
        logger = get_logger(adw_id)
        response = execute_prompt_raw(
            prompt=issue_description.lstrip(),
            issue_id=issue_id,
            adw_id=adw_id,
            agent_name=AGENT_PLAN_IMPLEMENTOR,
            model="opus",
            json_schema=IMPLEMENT_JSON_SCHEMA,
            prompt_label="implement-direct",
        )

        logger.debug(
            "implement-direct response: success=%s, session_id=%s",
            response.success,
            response.session_id,
        )

        if not response.success:
            error_message = response.output or "Implement-direct step failed"
            return StepResult.fail(error_message)

        if not response.output:
            return StepResult.fail("Implement-direct step returned empty output")

        parse_result = parse_and_validate_json(
            response.output, IMPLEMENT_REQUIRED_FIELDS, step_name="implement-direct"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        raw_repos = (parse_result.data or {}).get("affected_repos", [])
        try:
            repo_details = [RepoChangeDetail(**r) for r in raw_repos] if raw_repos else []
        except (ValidationError, TypeError):
            logger.warning(
                "Could not parse affected_repos from LLM output, continuing without repo details"
            )
            repo_details = []

        return StepResult.ok(
            ImplementData(
                output=response.output,
                session_id=response.session_id,
                affected_repos=repo_details,
            ),
            parsed_data=parse_result.data,
        )

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement directly from the issue description and store result.

        Args:
            context: Workflow context with fetch-issue artifact

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load issue from fetch-issue artifact (required)
        try:
            issue = context.load_required_artifact(
                "issue",
                "fetch-issue",
                FetchIssueArtifact,
                lambda a: a.issue,
            )
        except StepInputError as e:
            logger.error("Cannot implement: no issue available: %s", e)
            return StepResult.fail(
                f"Cannot implement: no issue available: {e}",
                rerun_from="Fetching issue",
            )

        if issue is None or not issue.description:
            logger.error("Cannot implement: issue has no description")
            return StepResult.fail(
                "Cannot implement: issue has no description",
                rerun_from="Fetching issue",
            )

        implement_response = self._implement_direct(
            issue.description, context.require_issue_id, context.adw_id
        )

        if not implement_response.success:
            logger.error("Error implementing solution: %s", implement_response.error)
            return StepResult.fail(f"Error implementing solution: {implement_response.error}")

        logger.info("Direct solution implemented")

        if implement_response.data is None:
            logger.error("Implementation data missing despite successful response")
            return StepResult.fail("Implementation data missing despite successful response")

        logger.debug("Output preview: %s...", implement_response.data.output[:200])

        # Store implementation data in context
        context.data["implement_data"] = implement_response.data

        # Save artifact
        artifact = ImplementArtifact(
            workflow_id=context.adw_id,
            implement_data=implement_response.data,
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved implementation artifact for workflow %s", context.adw_id)

        status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
        log_artifact_comment_status(status, msg)

        self._finalize_workflow(context)

        return StepResult.ok(None)

    def _finalize_workflow(self, context: WorkflowContext) -> None:
        logger = get_logger(context.adw_id)
        update_status(context.require_issue_id, "completed", adw_id=context.adw_id)
        payload = CommentPayload(
            issue_id=context.require_issue_id,
            adw_id=context.adw_id,
            text="Solution implemented successfully",
            raw={"text": "Solution implemented successfully."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)
