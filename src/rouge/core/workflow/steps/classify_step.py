"""Classify issue step implementation."""

import logging
from typing import cast

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import ClassificationArtifact, IssueArtifact
from rouge.core.workflow.shared import AGENT_CLASSIFIER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ClassifyData, PlanSlashCommand, StepResult

logger = logging.getLogger(__name__)

# Required fields for classification output JSON
CLASSIFY_REQUIRED_FIELDS = {
    "type": str,
    "level": str,
    "output": str,
}

CLASSIFY_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "level": {
      "type": "string",
      "enum": ["simple", "average", "complex", "critical"]
    },
    "output": { "type": "string", "const": "classify" },
    "type": { "type": "string", "enum": ["bug", "chore", "feature"] }
  },
  "required": ["level", "output", "type"]
}"""


class ClassifyStep(WorkflowStep):
    """Classify issue and determine workflow command."""

    @property
    def name(self) -> str:
        return "Classifying issue"

    def _classify_issue(
        self,
        issue: Issue,
        adw_id: str,
    ) -> StepResult[ClassifyData]:
        """Classify issue and return appropriate slash command.

        Args:
            issue: The issue to classify
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with ClassifyData containing command and classification
        """
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_CLASSIFIER,
            slash_command="/adw-classify",
            args=[issue.description],
            adw_id=adw_id,
            issue_id=issue.id,
            model="sonnet",
            json_schema=CLASSIFY_JSON_SCHEMA,
        )
        logger.debug(
            "classify request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )
        response = execute_template(request)
        logger.debug(
            "classify response: %s",
            response.model_dump_json(indent=2, by_alias=True),
        )

        if not response.success:
            return StepResult.fail(response.output or "Agent failed without output")

        logger.debug("Classifier raw output: %s", response.output)

        # Parse and validate JSON output using the shared helper
        parse_result = parse_and_validate_json(
            response.output, CLASSIFY_REQUIRED_FIELDS, step_name="classify"
        )
        if not parse_result.success:
            return StepResult.fail(f"Invalid classification JSON: {parse_result.error}")

        # parse_result.data is guaranteed to be non-None after success check
        classification_data = parse_result.data
        assert (
            classification_data is not None
        ), "classification_data should not be None after success check"

        # Validate output field
        if classification_data.get("output") != "classify":
            return StepResult.fail("Invalid output field in classification")

        issue_type = classification_data["type"]
        complexity_level = classification_data["level"]

        normalized_type = issue_type.strip().lower()
        normalized_level = complexity_level.strip().lower()

        valid_types = {"chore", "bug", "feature"}
        valid_levels = {"simple", "average", "complex", "critical"}

        if normalized_type not in valid_types:
            return StepResult.fail(f"Invalid issue type selected: {issue_type}")
        if normalized_level not in valid_levels:
            return StepResult.fail(f"Invalid complexity level selected: {complexity_level}")

        triage_command = cast(PlanSlashCommand, f"/adw-{normalized_type}-plan")
        normalized_classification = {
            "type": normalized_type,
            "level": normalized_level,
        }

        return StepResult.ok(
            ClassifyData(command=triage_command, classification=normalized_classification)
        )

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

        result = self._classify_issue(issue, context.adw_id)

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
