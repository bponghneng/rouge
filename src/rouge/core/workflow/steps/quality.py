"""Code quality step implementation."""

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.notifications import make_progress_comment_handler
from rouge.core.workflow.shared import AGENT_CODE_QUALITY_CHECKER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

# Required fields for code quality output JSON
CODE_QUALITY_REQUIRED_FIELDS = {
    "output": str,
    "tools": list,
}


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
        logger = context.logger

        try:
            quality_handler = make_progress_comment_handler(
                context.issue_id, context.adw_id, logger
            )

            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_CODE_QUALITY_CHECKER,
                slash_command="/adw-code-quality",
                args=[],
                adw_id=context.adw_id,
                issue_id=context.issue_id,
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
                return StepResult.fail(f"Code quality checks failed: {response.output}")

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output,
                CODE_QUALITY_REQUIRED_FIELDS,
                logger,
                step_name="code_quality",
            )
            if not parse_result.success:
                return StepResult.fail(parse_result.error or "JSON parsing failed")

            logger.info("Code quality checks completed successfully")

            # Insert progress comment - best-effort, non-blocking
            emit_progress_comment(
                context.issue_id,
                "Code quality checks completed.",
                logger,
                raw={
                    "text": "Code quality checks completed.",
                    "result": parse_result.data,
                },
            )

            return StepResult.ok(None, parsed_data=parse_result.data)

        except Exception as e:
            logger.warning(f"Code quality step failed: {e}")
            return StepResult.fail(f"Code quality step failed: {e}")
