"""Implementation step."""

import os

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ImplementArtifact,
    PlanArtifact,
)
from rouge.core.workflow.repo_filter import detect_affected_repos
from rouge.core.workflow.shared import AGENT_PLAN_IMPLEMENTOR, IMPLEMENT_STEP_NAME
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import emit_and_log
from rouge.core.workflow.types import ImplementData, RepoChangeEntry, StepResult

# Required fields for implement output JSON
IMPLEMENT_REQUIRED_FIELDS = {
    "files_modified": list,
    "git_diff_stat": str,
    "output": str,
    "status": str,
    "summary": str,
}

IMPLEMENT_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "files_modified": { "type": "array", "items": { "type": "string" } },
    "git_diff_stat": { "type": "string" },
    "output": { "type": "string", "enum": ["implement-plan"] },
    "status": { "type": "string" },
    "summary": { "type": "string" }
  },
  "required": ["files_modified", "git_diff_stat", "output", "status", "summary"]
}"""


class ImplementStep(WorkflowStep):
    """Execute implementation of the plan."""

    def __init__(self, plan_step_name: str | None = None) -> None:
        """Initialize ImplementStep.

        Args:
            plan_step_name: Name of the preceding plan step for rerun messages.
                Defaults to "Building implementation plan" when not provided.
        """
        self.plan_step_name = plan_step_name or "Building implementation plan"

    @property
    def name(self) -> str:
        return IMPLEMENT_STEP_NAME

    def _implement_plan(
        self, plan_content: str, issue_id: int, adw_id: str
    ) -> StepResult[ImplementData]:
        """Implement the plan using Claude Code template.

        Uses the implement-plan prompt template via execute_template pattern.

        Args:
            plan_content: The plan content (markdown) to implement
            issue_id: Issue ID for tracking
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with ImplementData containing output and optional session_id
        """
        logger = get_logger(adw_id)
        # Create template request using packaged prompt
        request = ClaudeAgentTemplateRequest(
            prompt_id=PromptId.IMPLEMENT_PLAN,
            args=[plan_content.lstrip()],
            issue_id=issue_id,
            adw_id=adw_id,
            agent_name=AGENT_PLAN_IMPLEMENTOR,
            json_schema=IMPLEMENT_JSON_SCHEMA,
        )

        # Execute template
        response = execute_template(request)

        logger.debug(
            "implement response: success=%s, session_id=%s",
            response.success,
            response.session_id,
        )

        if not response.success:
            error_message = response.output or "Implement step failed"
            return StepResult.fail(error_message)

        # Guard: Check that response.output is present before parsing
        if not response.output:
            return StepResult.fail("Implement step returned empty output")

        # Parse and validate JSON output with IMPLEMENT_REQUIRED_FIELDS
        parse_result = parse_and_validate_json(
            response.output, IMPLEMENT_REQUIRED_FIELDS, step_name="implement"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        parsed = parse_result.data or {}
        files_modified = parsed.get("files_modified", [])
        git_diff_stat = parsed.get("git_diff_stat", "")
        summary = parsed.get("summary", "")

        return StepResult.ok(
            ImplementData(
                output=response.output,
                session_id=response.session_id,
                files_modified=files_modified,
                git_diff_stat=git_diff_stat,
                summary=summary,
            ),
            parsed_data=parse_result.data,
        )

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement the plan and store result in context.

        Args:
            context: Workflow context with plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load plan from artifact (required)
        try:
            plan_data = context.load_required_artifact(
                "plan_data",
                "plan",
                PlanArtifact,
                lambda a: a.plan_data,
            )
        except StepInputError as e:
            logger.error("Cannot implement: no plan available: %s", e)
            return StepResult.fail(
                f"Cannot implement: no plan available: {e}",
                rerun_from=self.plan_step_name,
            )
        plan_text = plan_data.plan if plan_data is not None else None

        if plan_text is None:
            logger.error("Cannot implement: no plan available")
            return StepResult.fail(
                "Cannot implement: no plan available",
                rerun_from=self.plan_step_name,
            )

        implement_response = self._implement_plan(
            plan_text, context.require_issue_id, context.adw_id
        )

        if not implement_response.success:
            logger.error("Error implementing solution: %s", implement_response.error)
            return StepResult.fail(f"Error implementing solution: {implement_response.error}")

        logger.info("Solution implemented")

        if implement_response.data is None:
            logger.error("Implementation data missing despite successful response")
            return StepResult.fail("Implementation data missing despite successful response")

        # Derive affected_repos and per-repo entries from files_modified
        repos_map: dict[str, list[str]] = {}
        for f_raw in implement_response.data.files_modified:
            f = os.path.normpath(f_raw)
            # Reject absolute paths — normpath resolves '..' so an LLM-supplied path
            # like /repo/alpha/../../../etc/passwd becomes /etc/passwd (no '..' left).
            # Rejecting absolute paths after normpath catches all such traversals.
            if os.path.isabs(f):
                logger.debug("Skipping absolute path: %s", f_raw)
                continue
            # Skip relative paths that still escape via traversal (e.g., ../foo)
            if ".." in f.split(os.sep):
                logger.debug("Skipping path with traversal component: %s", f_raw)
                continue
            for rp in sorted(context.repo_paths, key=len, reverse=True):
                if f.startswith(rp + os.sep) or os.path.isfile(os.path.join(rp, f)):
                    repos_map.setdefault(rp, []).append(f)
                    break

        # Fallback: use git diff detection if files_modified is empty
        if not repos_map and context.repo_paths:
            detected = detect_affected_repos(context.repo_paths, context.adw_id)
            for rp in detected:
                repos_map[rp] = []

        affected_repos = [rp for rp in context.repo_paths if rp in repos_map]
        repo_entries = [
            RepoChangeEntry(repo_path=rp, files_modified=repos_map.get(rp, []))
            for rp in affected_repos
        ]

        # Update the implement data with derived fields
        implement_response.data.affected_repos = affected_repos
        implement_response.data.repos = repo_entries

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

        # Insert progress comment - best-effort, non-blocking
        emit_and_log(
            context.require_issue_id,
            context.adw_id,
            "Implementation complete.",
            {"text": "Implementation complete."},
        )

        return StepResult.ok(None)
