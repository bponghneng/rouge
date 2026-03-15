"""Review addressing step implementation."""

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import CodeReviewArtifact, ReviewFixArtifact
from rouge.core.workflow.shared import CODE_REVIEW_STEP_NAME
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import _sanitize_for_logging
from rouge.core.workflow.types import RepoFixResult, StepResult

# Required fields for address review output JSON
ADDRESS_REVIEW_REQUIRED_FIELDS = {
    "issues": list,
    "output": str,
    "summary": str,
}

ADDRESS_REVIEW_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["file", "lines", "type", "status", "notes"],
        "properties": {
          "file": { "type": "string" },
          "lines": { "type": "string" },
          "type": { "type": "string" },
          "status": { "type": "string", "enum": ["fixed", "skipped", "needs-followup"] },
          "notes": { "type": "string" }
        }
      }
    },
    "output": { "type": "string", "const": "implement-review" },
    "summary": { "type": "string" }
  },
  "required": ["issues", "output", "summary"]
}"""


class ReviewFixStep(WorkflowStep):
    """Address review issues from CodeRabbit review."""

    @property
    def name(self) -> str:
        return "Addressing review issues"

    @property
    def is_critical(self) -> bool:
        # Addressing review is not critical - workflow continues if it fails
        return False

    def _address_review_issues(
        self,
        issue_id: int | None,
        adw_id: str,
        review_text: str,
    ) -> StepResult:
        """Address issues found in the review.

        This step runs the implement-review prompt template to address
        the issues identified in the review step.

        Args:
            issue_id: Optional Issue ID (None for standalone review)
            adw_id: ADW workflow ID
            review_text: The review text containing issues to address

        Returns:
            StepResult indicating success or failure
        """
        logger = get_logger(adw_id)
        logger.info("Addressing review issues for issue %s (adw_id=%s)", issue_id, adw_id)

        if not review_text or not review_text.strip():
            logger.error("Review text is empty")
            return StepResult.fail("Review text is empty")

        try:
            # Construct the template request
            # Pass the review text as an argument to the prompt template
            request = ClaudeAgentTemplateRequest(
                agent_name="code_review",
                prompt_id=PromptId.IMPLEMENT_REVIEW,
                args=[review_text],
                adw_id=adw_id,
                issue_id=issue_id,
                model="sonnet",
                json_schema=ADDRESS_REVIEW_JSON_SCHEMA,
            )

            logger.debug(
                "address_review request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            # Execute the template
            response = execute_template(request, require_json=True)

            logger.debug("address_review response: success=%s", response.success)

            # Emit progress comment
            payload = CommentPayload(
                issue_id=issue_id,
                text="Addressing review issues...",
                raw={
                    "output": "address-review-response",
                    "llm_response": _sanitize_for_logging(response.output),
                },
                source="system",
                kind="workflow",
                adw_id=adw_id,
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            if not response.success:
                logger.error(
                    "Failed to execute %s template: %s",
                    PromptId.IMPLEMENT_REVIEW.value,
                    response.output,
                )
                return StepResult.fail(
                    f"Failed to execute {PromptId.IMPLEMENT_REVIEW.value} template: "
                    f"{response.output}"
                )

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output,
                ADDRESS_REVIEW_REQUIRED_FIELDS,
                step_name="address_review",
            )
            if not parse_result.success:
                return StepResult.fail(parse_result.error or "JSON parsing failed")

            logger.info("Review issues addressed successfully")

            # Emit result comment
            parsed_data = parse_result.data or {}
            result_payload = CommentPayload(
                issue_id=issue_id,
                text="Review issues addressed",
                raw={
                    "output": parsed_data.get("output", ""),
                    "summary": parsed_data.get("summary", ""),
                    "issues": parsed_data.get("issues", []),
                    "parsed_data": parsed_data,
                },
                source="system",
                kind="address_review",
                adw_id=adw_id,
            )
            status, msg = emit_comment_from_payload(result_payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            return StepResult.ok(None, parsed_data=parse_result.data)

        except Exception as e:
            logger.exception("Failed to address review issues")
            return StepResult.fail(f"Failed to address review issues: {e}")

    def run(self, context: WorkflowContext) -> StepResult:
        """Address review issues on a per-repo basis.

        If the review was clean (no actionable issues), returns early with
        a success result.  Otherwise filters to dirty repos that are under
        the rerun limit, concatenates their review texts with repo-path
        headers, and passes the combined string to ``_address_review_issues``.

        Rerun tracking is per-repo via ``RepoReviewResult.rerun_count``,
        persisted in the ``CodeReviewArtifact``.  The volatile
        ``context.data`` counter is not used.

        Args:
            context: Workflow context with review_data

        Returns:
            StepResult with success status and optional error message.
            When issues are addressed and budget remains, ``rerun_from`` is
            set to the CodeReviewStep name so the pipeline re-reviews.
        """
        logger = get_logger(context.adw_id)

        # Default max iterations for review/fix cycle
        MAX_REVIEW_ITERATIONS = 5

        # Load review artifact early (required)
        try:
            artifact = context.artifact_store.read_artifact("code-review", CodeReviewArtifact)
        except FileNotFoundError as e:
            logger.warning("Missing required code-review artifact: %s", e)
            return StepResult.fail("Missing required code-review artifact")
        except ValueError as e:
            logger.warning("Corrupted code-review artifact: %s", e)
            return StepResult.fail("Corrupted code-review artifact")

        # Short-circuit: nothing to do when the review is clean
        if artifact.is_clean:
            logger.info("Review is clean, no issues to address")
            return StepResult.ok(None)

        # Filter to non-clean repos
        dirty_repos = [r for r in artifact.repo_reviews if not r.is_clean]

        if not dirty_repos:
            logger.info("No dirty repos found despite aggregate is_clean=False, skipping")
            return StepResult.ok(None)

        # Check per-repo rerun limits; separate under-limit from over-limit
        actionable_repos = []
        for r in dirty_repos:
            if r.rerun_count >= MAX_REVIEW_ITERATIONS:
                logger.warning(
                    "Repo %s has reached max review/fix iterations (%s), skipping",
                    r.repo_path,
                    MAX_REVIEW_ITERATIONS,
                )
            else:
                actionable_repos.append(r)

        # If all dirty repos have hit their limit, no rerun needed
        if not actionable_repos:
            logger.warning(
                "All dirty repos have reached max iterations (%s), continuing workflow",
                MAX_REVIEW_ITERATIONS,
            )
            fix_artifact = ReviewFixArtifact(
                workflow_id=context.adw_id,
                success=True,
                message=(f"All dirty repos reached max iterations ({MAX_REVIEW_ITERATIONS})"),
                repo_fixes=[
                    RepoFixResult(
                        repo_path=r.repo_path,
                        success=True,
                        message=f"Max iterations ({MAX_REVIEW_ITERATIONS}) reached",
                    )
                    for r in dirty_repos
                ],
            )
            context.artifact_store.write_artifact(fix_artifact)

            status, msg = emit_artifact_comment(context.issue_id, context.adw_id, fix_artifact)
            log_artifact_comment_status(status, msg)

            return StepResult.ok(None)

        # Concatenate review texts with repo-path headers
        review_sections = []
        for r in actionable_repos:
            text = r.review_text.strip()
            if text:
                review_sections.append(f"## {r.repo_path}\n{text}")

        combined_review_text = "\n\n".join(review_sections)

        if not combined_review_text:
            logger.warning("No review text available from dirty repos, skipping")
            return StepResult.ok(None)

        # Pass concatenated string to the existing fix method
        review_issues_result = self._address_review_issues(
            context.issue_id,
            context.adw_id,
            combined_review_text,
        )

        if not review_issues_result.success:
            logger.error("Failed to address review issues: %s", review_issues_result.error)
            fix_artifact = ReviewFixArtifact(
                workflow_id=context.adw_id,
                success=False,
                message=review_issues_result.error,
                repo_fixes=[
                    RepoFixResult(
                        repo_path=r.repo_path,
                        success=False,
                        message=review_issues_result.error or "Failed to address review issues",
                    )
                    for r in actionable_repos
                ],
            )
            context.artifact_store.write_artifact(fix_artifact)

            status, msg = emit_artifact_comment(context.issue_id, context.adw_id, fix_artifact)
            log_artifact_comment_status(status, msg)
            return StepResult.fail(f"Failed to address review issues: {review_issues_result.error}")

        logger.info("Review issues addressed successfully")

        # Increment rerun_count for each actionable dirty repo in the artifact
        actionable_paths = {r.repo_path for r in actionable_repos}
        for r in artifact.repo_reviews:
            if r.repo_path in actionable_paths:
                r.rerun_count += 1

        # Write back updated CodeReviewArtifact with incremented rerun counts
        context.artifact_store.write_artifact(artifact)

        # Build repo_fixes list
        repo_fixes = [
            RepoFixResult(
                repo_path=r.repo_path,
                success=True,
                message="Review issues addressed",
            )
            for r in actionable_repos
        ]

        # Determine if any repo still needs re-review (under limit after increment)
        still_dirty = any(
            not r.is_clean and r.rerun_count < MAX_REVIEW_ITERATIONS for r in artifact.repo_reviews
        )

        if not still_dirty:
            logger.info("All repos are either clean or at max iterations, continuing workflow")
            fix_artifact = ReviewFixArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Review issues addressed, all repos clean or at max iterations",
                repo_fixes=repo_fixes,
            )
            context.artifact_store.write_artifact(fix_artifact)

            status, msg = emit_artifact_comment(context.issue_id, context.adw_id, fix_artifact)
            log_artifact_comment_status(status, msg)

            return StepResult.ok(None)

        # Budget remains for at least one repo, request re-review
        logger.info("Requesting re-review for repos still needing fixes")

        fix_artifact = ReviewFixArtifact(
            workflow_id=context.adw_id,
            success=True,
            message="Review issues addressed, re-running review",
            repo_fixes=repo_fixes,
        )
        context.artifact_store.write_artifact(fix_artifact)
        logger.debug("Saved review-fix artifact for workflow %s", context.adw_id)

        status, msg = emit_artifact_comment(context.issue_id, context.adw_id, fix_artifact)
        log_artifact_comment_status(status, msg)

        # Insert progress comment - best-effort, non-blocking
        if context.issue_id is not None:
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text="Review issues addressed, re-running review.",
                raw={
                    "text": "Review issues addressed, re-running review.",
                    "repos_fixed": [r.repo_path for r in actionable_repos],
                },
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            elif status == "skipped":
                logger.debug(msg)
            else:
                logger.error(msg)

        return StepResult.ok(None, rerun_from=CODE_REVIEW_STEP_NAME)
