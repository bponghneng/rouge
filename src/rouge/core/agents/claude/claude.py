"""Claude Code provider implementation.

This module extracts all Claude Code-specific logic from the original agent.py
into a dedicated provider implementation. It handles CLI invocation, subprocess
management, and JSON envelope parsing from stdout.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from rouge.core.agents.base import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    CodingAgent,
)

# Load environment variables
load_dotenv()

# Get Claude Code CLI path from environment
CLAUDE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

_DEFAULT_LOGGER = logging.getLogger(__name__)


def check_claude_installed() -> Optional[str]:
    """Check if Claude Code CLI is installed. Return error message if not."""
    try:
        result = subprocess.run([CLAUDE_PATH, "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    except FileNotFoundError:
        return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    return None


def get_claude_env() -> Dict[str, str]:
    """Get only the required environment variables for Claude Code execution.

    Returns a dictionary containing only the necessary environment variables
    based on .env.sample configuration.

    Subprocess env behavior:
    - env=None -> Inherits parent's environment (default)
    - env={} -> Empty environment (no variables)
    - env=custom_dict -> Only uses specified variables

    So this will work with gh authentication:
    # These are equivalent:
    result = subprocess.run(cmd, capture_output=True, text=True)
    result = subprocess.run(cmd, capture_output=True, text=True, env=None)

    But this will NOT work (no PATH, no auth):
    result = subprocess.run(cmd, capture_output=True, text=True, env={})
    """
    required_env_vars = {
        # Anthropic Configuration (required)
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        # Claude Code Configuration
        "CLAUDE_CODE_PATH": os.getenv("CLAUDE_CODE_PATH", "claude"),
        "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": os.getenv(
            "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR", "true"
        ),
        # Agent Cloud Sandbox Environment (optional)
        "E2B_API_KEY": os.getenv("E2B_API_KEY"),
        # Basic environment variables Claude Code might need
        "HOME": os.getenv("HOME"),
        "USER": os.getenv("USER"),
        "PATH": os.getenv("PATH"),
        "SHELL": os.getenv("SHELL"),
        "TERM": os.getenv("TERM"),
    }

    # Only add GitHub tokens if GITHUB_PAT exists
    github_pat = os.getenv("GITHUB_PAT")
    if github_pat:
        required_env_vars["GITHUB_PAT"] = github_pat
        required_env_vars["GH_TOKEN"] = github_pat  # Claude Code uses GH_TOKEN

    # Filter out None values
    return {k: v for k, v in required_env_vars.items() if v is not None}


def save_prompt(prompt: str, adw_id: str, agent_name: str = "ops") -> None:
    """Save a prompt to the appropriate logging directory."""
    # Extract slash command from prompt
    match = re.match(r"^(/\w+)", prompt)
    if not match:
        return

    slash_command = match.group(1)
    # Remove leading slash for filename
    command_name = slash_command[1:]

    # Create directory structure using get_working_dir() as base
    from rouge.core.workflow.shared import get_working_dir

    prompt_dir = Path(get_working_dir()) / ".rouge/agents/logs" / adw_id / agent_name / "prompts"
    os.makedirs(str(prompt_dir), exist_ok=True)

    # Save prompt to file
    prompt_file = prompt_dir / f"{command_name}.txt"
    with open(str(prompt_file), "w") as f:
        f.write(prompt)

    _DEFAULT_LOGGER.debug("Saved prompt to: %s", prompt_file)


class ClaudeAgent(CodingAgent):
    """Claude Code CLI provider implementation.

    This class integrates the Claude Code CLI as a coding agent provider,
    handling subprocess execution and JSON envelope parsing.

    Key features:
    - Uses subprocess.run with --output-format json for synchronous execution
    - Supports --json-schema for structured output validation
    - Parses JSON envelope to extract structured_output
    - Session ID extraction from envelope metadata
    - Error handling for invalid envelopes and execution failures
    """

    def execute_prompt(
        self,
        request: AgentExecuteRequest,
    ) -> AgentExecuteResponse:
        """Execute Claude Code CLI with the given request.

        This method handles the complete lifecycle:
        1. Map AgentExecuteRequest to Claude-specific parameters
        2. Validate CLI is installed
        3. Save prompt for logging
        4. Execute subprocess with subprocess.run
        5. Parse JSON envelope from stdout
        6. Map back to AgentExecuteResponse

        Args:
            request: Provider-agnostic execution request

        Returns:
            Structured response with results and metadata
        """
        try:
            # Map to Claude-specific model
            model = request.provider_options.get("model", request.model or "opus")
            dangerously_skip_permissions = request.provider_options.get(
                "dangerously_skip_permissions", True
            )
            json_schema = request.provider_options.get("json_schema")

            # Check if Claude Code CLI is installed
            error_msg = check_claude_installed()
            if error_msg:
                return AgentExecuteResponse(
                    output=error_msg,
                    success=False,
                    session_id=None,
                    raw_output_path=None,
                    error_detail=error_msg,
                )

            # Save prompt before execution
            save_prompt(request.prompt, request.adw_id, request.agent_name)

            # Build command - use json format (not stream-json)
            cmd = [CLAUDE_PATH, "-p", request.prompt]
            cmd.extend(["--model", model])
            cmd.extend(["--output-format", "json"])
            if json_schema:
                cmd.extend(["--json-schema", json_schema])
            if dangerously_skip_permissions:
                cmd.append("--dangerously-skip-permissions")

            # Use current environment for subprocess
            env = os.environ.copy()

            # Import here to avoid circular dependency
            from rouge.core.workflow.shared import get_working_dir

            # Execute subprocess
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=get_working_dir(),
            )

            # Parse JSON envelope from stdout
            return self._parse_json_envelope(result)

        except Exception as e:
            error_msg = f"Error executing Claude Code: {e}"
            _DEFAULT_LOGGER.exception(error_msg)
            return AgentExecuteResponse(
                output=error_msg,
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=str(e),
            )

    def _parse_json_envelope(
        self, result: subprocess.CompletedProcess[str]
    ) -> AgentExecuteResponse:
        """Parse JSON envelope from Claude Code CLI output.

        Expected envelope structure:
        {
            "type": "result",
            "subtype": "success" | "error_max_turns" | ...,
            "is_error": false,
            "session_id": "...",
            "duration_ms": 12345,
            "structured_output": { ... }  // or serialized JSON string
        }

        Args:
            result: Completed subprocess result with stdout/stderr

        Returns:
            AgentExecuteResponse with parsed data or error details
        """
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Handle empty stdout
        if not stdout:
            error_detail = stderr if stderr else f"Process exited with code {result.returncode}"
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=error_detail,
            )

        # Parse JSON envelope
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as e:
            error_detail = f"Invalid JSON in Claude Code output: {e}"
            _DEFAULT_LOGGER.error("%s. Raw output: %s", error_detail, stdout[:500])
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=error_detail,
            )

        # Validate envelope structure
        if not isinstance(envelope, dict):
            error_detail = f"Expected JSON object, got {type(envelope).__name__}"
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=error_detail,
            )

        envelope_type = envelope.get("type")
        if envelope_type != "result":
            error_detail = f"Expected envelope type 'result', got '{envelope_type}'"
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=envelope.get("session_id"),
                raw_output_path=None,
                error_detail=error_detail,
            )

        # Extract metadata
        session_id = envelope.get("session_id")
        duration_ms = envelope.get("duration_ms")
        subtype = envelope.get("subtype")
        is_error = envelope.get("is_error", False)

        # Log warning for non-success subtypes
        if subtype and subtype != "success":
            _DEFAULT_LOGGER.warning(
                "Claude Code returned subtype '%s' (session_id=%s, duration_ms=%s)",
                subtype,
                session_id,
                duration_ms,
            )

        # Check for hard error
        if is_error:
            error_text = envelope.get("result", "Unknown error")
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_text}",
                success=False,
                session_id=session_id,
                raw_output_path=None,
                error_detail=error_text,
            )

        # Extract structured_output
        structured_output = envelope.get("structured_output")
        if structured_output is None:
            error_detail = "Missing 'structured_output' in envelope"
            _DEFAULT_LOGGER.error("%s. Envelope keys: %s", error_detail, list(envelope.keys()))
            return AgentExecuteResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=session_id,
                raw_output_path=None,
                error_detail=error_detail,
            )

        # Serialize structured_output to JSON string if it's not already a string
        if isinstance(structured_output, str):
            output = structured_output
        else:
            output = json.dumps(structured_output)

        return AgentExecuteResponse(
            output=output,
            success=True,
            session_id=session_id,
            raw_output_path=None,
            error_detail=None,
        )
