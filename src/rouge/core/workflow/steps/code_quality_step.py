"""Code quality step implementation."""

import logging

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.workflow.artifacts import CodeQualityArtifact
from rouge.core.workflow.shared import AGENT_CODE_QUALITY_CHECKER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Required fields for code quality output JSON
CODE_QUALITY_REQUIRED_FIELDS = {
    "output": str,
    "tools": list,
}

CODE_QUALITY_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "required": ["file", "issue"],
        "properties": {
          "file": { "type": "string" },
          "issue": { "type": "string" }
        }
      }
    },
    "output": { "type": "string", "const": "code-quality" },
    "tools": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["issues", "output", "tools"]
}"""


class CodeQualityStep(WorkflowStep):
    """Run code quality checks via /adw-code-quality slash command."""

    @property
    def name(self) -> str:
        return "Running code quality checks"

    @property
    def is_critical(self) -> bool:
        # Code quality is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Run code quality checks.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        try:
            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_CODE_QUALITY_CHECKER,
                slash_command="/adw-code-quality",
                args=[],
                adw_id=context.adw_id,
                issue_id=context.issue_id,
                model="sonnet",
                json_schema=CODE_QUALITY_JSON_SCHEMA,
            )

            logger.debug(
                "code_quality request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            response = execute_template(request)

            logger.debug("code_quality response: success=%s", response.success)

            if not response.success:
                logger.warning("Code quality checks failed: %s", response.output)
                return StepResult.fail(f"Code quality checks failed: {response.output}")

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output,
                CODE_QUALITY_REQUIRED_FIELDS,
                step_name="code_quality",
            )
            if not parse_result.success:
                return StepResult.fail(parse_result.error or "JSON parsing failed")

            logger.info("Code quality checks completed successfully")

            # Save artifact if artifact store is available
            if (
                context.artifacts_enabled
                and context.artifact_store is not None
                and parse_result.data is not None
            ):
                artifact = CodeQualityArtifact(
                    workflow_id=context.adw_id,
                    output=parse_result.data.get("output", ""),
                    tools=parse_result.data.get("tools", []),
                    parsed_data=parse_result.data,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved quality_check artifact for workflow %s", context.adw_id)

                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                log_artifact_comment_status(status, msg)

            # Insert progress comment - best-effort, non-blocking
            if context.issue_id is not None:
                payload = CommentPayload(
                    issue_id=context.issue_id,
                    adw_id=context.adw_id,
                    text="Code quality checks completed.",
                    raw={
                        "text": "Code quality checks completed.",
                        "result": parse_result.data,
                    },
                    source="system",
                    kind="workflow",
                )
                status, msg = emit_comment_from_payload(payload)
                if status == "success":
                    logger.debug(msg)
                else:
                    logger.error(msg)

            return StepResult.ok(None, parsed_data=parse_result.data)

        except Exception as e:
            logger.warning("Code quality step failed: %s", e)
            return StepResult.fail(f"Code quality step failed: {e}")
