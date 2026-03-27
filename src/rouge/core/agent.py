"""Provider-agnostic agent execution facade.

This module provides a backward-compatible facade over the agent registry,
maintaining the original API while delegating to the new abstraction layer.

For new code, prefer importing from rouge.core.agents directly:
    from rouge.core.agents import get_agent, AgentExecuteRequest
"""

import logging

from rouge.core.agents import (
    AgentExecuteRequest,
    get_agent,
)
from rouge.core.agents.claude import (
    ClaudeAgentPromptResponse,
    ClaudeAgentTemplateRequest,
)
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.prompts import render_prompt

logger = logging.getLogger(__name__)

# Required fields for agent output JSON
# Agent output must have output
AGENT_REQUIRED_FIELDS = {"output": str}


def execute_template(
    request: ClaudeAgentTemplateRequest,
    *,
    require_json: bool = True,
) -> ClaudeAgentPromptResponse:
    """Execute a prompt template with prompt ID and arguments.

    This is a Claude-specific function that uses the Claude agent provider
    exclusively. It constructs an AgentExecuteRequest and calls the Claude
    agent's execute_prompt() directly. Enforces JSON parsing and emits progress
    comments with parsed data in the raw field.

    Args:
        request: Claude-specific template request
        require_json: If True (default), validates output as JSON and emits
            error comments for non-JSON output. If False, skips JSON validation
            and allows plain text output.

    Returns:
        Claude-specific prompt response
    """
    # Render prompt from packaged template
    rendered = render_prompt(request.prompt_id, request.args)

    # Model resolution priority:
    # 1. model_override (explicit caller intent) — wins unconditionally
    # 2. Template front matter model — preferred over the request default
    # 3. request.model default ("sonnet")
    effective_model = request.model_override or rendered.model or request.model

    # Build provider options
    provider_options: dict[str, object] = {"dangerously_skip_permissions": True}
    if request.json_schema:
        provider_options["json_schema"] = request.json_schema

    # Build AgentExecuteRequest
    agent_request = AgentExecuteRequest(
        prompt=rendered.text,
        issue_id=request.issue_id,
        adw_id=request.adw_id,
        agent_name=request.agent_name,
        prompt_label=request.prompt_id.value,
        model=effective_model,
        provider_options=provider_options,
    )

    # Get agent and execute directly
    agent = get_agent("claude")
    agent_response = agent.execute_prompt(agent_request)

    # Map to ClaudeAgentPromptResponse
    response = ClaudeAgentPromptResponse(
        output=agent_response.output,
        success=agent_response.success,
        session_id=agent_response.session_id,
    )

    # Handle JSON validation based on require_json parameter
    if response.success and response.output:
        raw_output = response.output.strip()

        prompt_label = request.prompt_id.value
        if require_json:
            # Use shared parser to sanitize and validate JSON
            result = parse_and_validate_json(
                raw_output,
                AGENT_REQUIRED_FIELDS,
                step_name=prompt_label,
            )
            if result.success:
                # Emit progress comment with parsed JSON in raw field
                payload = CommentPayload(
                    issue_id=request.issue_id,
                    text=f"Template {prompt_label} completed",
                    raw={"template": prompt_label, "result": result.data},
                    source="system",
                    kind="workflow",
                    adw_id=request.adw_id,
                )
                status, msg = emit_comment_from_payload(payload)
                logger.debug(msg) if status == "success" else logger.error(msg)
                logger.debug("Template output parsed as JSON successfully")
            else:
                # Emit error progress comment for non-JSON output
                logger.error("Template output is not valid JSON: %s", result.error)
                payload = CommentPayload(
                    issue_id=request.issue_id,
                    text=f"Template {prompt_label} returned non-JSON output",
                    raw={
                        "template": prompt_label,
                        "error": result.error,
                        "output": raw_output[:500],
                    },
                    source="system",
                    kind="workflow",
                    adw_id=request.adw_id,
                )
                status, msg = emit_comment_from_payload(payload)
                logger.debug(msg) if status == "success" else logger.error(msg)
        else:
            # Skip JSON validation for plain text output
            payload = CommentPayload(
                issue_id=request.issue_id,
                text=f"Template {prompt_label} completed",
                raw={"template": prompt_label, "output": raw_output[:500]},
                source="system",
                kind="workflow",
                adw_id=request.adw_id,
            )
            status, msg = emit_comment_from_payload(payload)
            logger.debug(msg) if status == "success" else logger.error(msg)
            logger.debug("Template output accepted as plain text (require_json=False)")

    return response
