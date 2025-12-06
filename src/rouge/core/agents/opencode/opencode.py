"""OpenCode provider implementation.

This module provides the OpenCode CLI integration for Rouge, allowing
OpenCode to be used as an alternative provider for the implementation step.
It follows the same architecture patterns as the Claude provider including
JSONL streaming, threading for subprocess management, and comprehensive
error handling.
"""

import json
import logging
import os
import subprocess
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from rouge.core.agents.base import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    CodingAgent,
)

# Load environment variables
load_dotenv()

# Get OpenCode CLI path from environment
OPENCODE_PATH = os.getenv("OPENCODE_PATH", "opencode")

_DEFAULT_LOGGER = logging.getLogger(__name__)


def check_opencode_installed() -> Optional[str]:
    """Check if OpenCode CLI is installed. Return error message if not.

    Returns:
        None if CLI is available, error message string if not
    """
    try:
        result = subprocess.run(
            [OPENCODE_PATH, "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return f"Error: OpenCode CLI is not installed. Expected at: {OPENCODE_PATH}"
    except FileNotFoundError:
        return f"Error: OpenCode CLI is not installed. Expected at: {OPENCODE_PATH}"
    except subprocess.TimeoutExpired:
        return f"Error: OpenCode CLI timeout. Check installation at: {OPENCODE_PATH}"
    return None


def get_opencode_env() -> Dict[str, str]:
    """Get required environment variables for OpenCode execution.

    Returns a dictionary containing only the necessary environment variables
    for OpenCode CLI execution.

    Returns:
        Dictionary of environment variables with None values filtered out
    """
    required_env_vars = {
        # OpenCode Configuration
        "OPENCODE_API_KEY": os.getenv("OPENCODE_API_KEY"),
        "OPENCODE_PATH": os.getenv("OPENCODE_PATH", "opencode"),
        # Basic environment variables OpenCode might need
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
        required_env_vars["GH_TOKEN"] = github_pat  # Forward as GH_TOKEN too

    # Filter out None values
    return {k: v for k, v in required_env_vars.items() if v is not None}


def parse_opencode_jsonl(
    output_file: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse OpenCode JSONL output file and return all messages and result message.

    Args:
        output_file: Path to the JSONL output file

    Returns:
        Tuple of (all_messages, result_message) where result_message is None if not found
    """
    try:
        with open(output_file, "r") as f:
            # Read all lines and parse each as JSON
            messages = []
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    messages.append(json.loads(stripped))
                except json.JSONDecodeError as e:
                    _DEFAULT_LOGGER.warning("Skipping malformed JSON line: %s", e)
                    continue

            # Find the result message (search backward for type="result")
            result_message = None
            for message in reversed(messages):
                if message.get("type") == "result":
                    result_message = message
                    break

            return messages, result_message
    except Exception as e:
        _DEFAULT_LOGGER.error("Error parsing JSONL file %s: %s", output_file, e)
        return [], None


def convert_jsonl_to_json(jsonl_file: str) -> str:
    """Convert JSONL file to JSON array file.

    Creates a .json file with the same name as the .jsonl file,
    containing all messages as a JSON array.

    Args:
        jsonl_file: Path to the JSONL file

    Returns:
        Path to the created JSON file
    """
    # Create JSON filename by replacing .jsonl with .json
    json_file = jsonl_file.replace(".jsonl", ".json")

    # Parse the JSONL file
    messages, _ = parse_opencode_jsonl(jsonl_file)

    # Write as JSON array
    with open(json_file, "w") as f:
        json.dump(messages, f, indent=2)

    _DEFAULT_LOGGER.debug("Created JSON file: %s", json_file)
    return json_file


def iter_opencode_items(line: str) -> List[Dict[str, Any]]:
    """Return text/tool items parsed from an OpenCode CLI stdout line.

    This helper filters OpenCode streaming lines into the simplified
    structures consumed by progress comment handlers.
    """
    items: List[Dict[str, Any]] = []

    stripped = line.strip()
    if not stripped:
        return items

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return items

    msg_type = parsed.get("type")
    if not msg_type:
        return items

    if msg_type == "text":
        part = parsed.get("part", {})
        if not isinstance(part, dict):
            return items

        text = part.get("text", "")
        if text:
            items.append({"type": "text", "text": text})

    elif msg_type == "tool_use":
        part = parsed.get("part", {})
        if not isinstance(part, dict):
            return items

        tool_name = part.get("tool")
        if tool_name:
            item: Dict[str, Any] = {
                "type": "tool_use",
                "name": tool_name,
            }

            state = part.get("state", {})
            if isinstance(state, dict) and "input" in state:
                item["input"] = state["input"]

            items.append(item)

    return items


class OpenCodeAgent(CodingAgent):
    """OpenCode CLI provider implementation.

    This class integrates the OpenCode CLI as a coding agent provider,
    handling subprocess execution, JSONL streaming, and result parsing.

    The implementation follows the same patterns as ClaudeAgent including:
    - Threading for stdout/stderr streaming
    - Session ID extraction with fallback logic
    - Directory structure conventions (.rouge/logs/agents/{adw_id}/{agent_name}/)
    - Error handling and timeout management
    """

    def execute_prompt(
        self,
        request: AgentExecuteRequest,
        *,
        stream_handler: Optional[Callable[[str], None]] = None,
    ) -> AgentExecuteResponse:
        """Execute OpenCode CLI with the given request.

        This method handles the complete lifecycle:
        1. Validate CLI is installed
        2. Determine output file path
        3. Execute subprocess with threading for streaming
        4. Parse JSONL results
        5. Map to AgentExecuteResponse

        Args:
            request: Provider-agnostic execution request
            stream_handler: Optional callback for streaming output lines

        Returns:
            Structured response with results and metadata
        """
        try:
            # Check if OpenCode CLI is installed
            error_msg = check_opencode_installed()
            if error_msg:
                return AgentExecuteResponse(
                    output=error_msg,
                    success=False,
                    session_id=None,
                    raw_output_path=None,
                    error_detail=error_msg,
                )

            # Determine output file path
            if request.output_path:
                output_file = request.output_path
            else:
                agents_dir = os.environ.get(
                    "ROUGE_AGENTS_DIR", os.path.join(os.getcwd(), ".rouge/logs/agents")
                )
                output_dir = os.path.join(agents_dir, request.adw_id, request.agent_name)
                output_file = os.path.join(output_dir, "raw_output.jsonl")

            # Create output directory if needed
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Extract model from provider options or use default
            model = request.provider_options.get("model", "zai-coding-plan/glm-4.6")

            # Build command - OpenCode CLI format
            # Note: OpenCode uses --command implement (NOT /implement)
            # Pass plan file content directly as prompt (no /implement prefix)
            cmd = [
                OPENCODE_PATH,
                "run",
                "--model",
                model,
                "--command",
                "implement",
                "--format",
                "json",
                request.prompt,
            ]

            _DEFAULT_LOGGER.debug("OpenCode command: %s", " ".join(cmd))

            # Get environment variables
            env = get_opencode_env()

            stderr_lines: List[str] = []

            with open(output_file, "w") as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )

                assert process.stdout is not None
                assert process.stderr is not None
                stdout_pipe = process.stdout
                stderr_pipe = process.stderr

                def _stream_stdout() -> None:
                    """Stream stdout to file and handler."""
                    for line in stdout_pipe:
                        f.write(line)
                        f.flush()
                        # Call stream handler if provided
                        if stream_handler:
                            try:
                                stream_handler(line)
                            except Exception as e:
                                _DEFAULT_LOGGER.error("Stream handler error: %s", e)
                    stdout_pipe.close()

                def _capture_stderr() -> None:
                    """Capture stderr for error reporting."""
                    for line in stderr_pipe:
                        stderr_lines.append(line)
                    stderr_pipe.close()

                # Start threads
                stdout_thread = threading.Thread(target=_stream_stdout, daemon=True)
                stderr_thread = threading.Thread(target=_capture_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                # Wait for process to complete
                process.wait()

                # Wait for threads to finish
                stdout_thread.join()
                stderr_thread.join()

            returncode = process.returncode or 0
            stderr_output = "".join(stderr_lines)

            # Parse results
            messages: List[Dict[str, Any]] = []
            result_message: Optional[Dict[str, Any]] = None
            if os.path.exists(output_file):
                messages, result_message = parse_opencode_jsonl(output_file)
                convert_jsonl_to_json(output_file)

                # Fallback: pick the last message if no result message found
                if not result_message and messages:
                    for message in reversed(messages):
                        if message.get("type") == "result" or message.get("session_id"):
                            result_message = message
                            break

            # Map results to AgentExecuteResponse
            if returncode == 0:
                if result_message:
                    session_id = result_message.get("session_id")
                    is_error = result_message.get("is_error", False)
                    result_text = result_message.get("result", "")

                    return AgentExecuteResponse(
                        output=result_text,
                        success=not is_error,
                        session_id=session_id,
                        raw_output_path=output_file,
                        error_detail=None if not is_error else result_text,
                    )

                # Fallback to last message
                if messages:
                    return AgentExecuteResponse(
                        output=json.dumps(messages[-1]),
                        success=True,
                        session_id=None,
                        raw_output_path=output_file,
                        error_detail=None,
                    )

                # Fallback to raw file content
                with open(output_file, "r") as f:
                    raw_output = f.read()
                return AgentExecuteResponse(
                    output=raw_output,
                    success=True,
                    session_id=None,
                    raw_output_path=output_file,
                    error_detail=None,
                )

            # Handle error case (returncode != 0)
            error_detail = stderr_output.strip()
            session_id = None
            if result_message:
                session_id = result_message.get("session_id")
                result_text = result_message.get("result", "").strip()
                if result_text:
                    error_detail = result_text
            elif messages:
                last_message = messages[-1]
                error_detail = (
                    last_message.get("result")
                    or last_message.get("error")
                    or json.dumps(last_message)
                )
            elif os.path.exists(output_file):
                with open(output_file, "r") as f:
                    file_content = f.read().strip()
                    if file_content:
                        error_detail = file_content

            if not error_detail:
                error_detail = f"Process exited with code {returncode}"

            error_msg = f"OpenCode error: {error_detail}"
            return AgentExecuteResponse(
                output=error_msg,
                success=False,
                session_id=session_id,
                raw_output_path=output_file if os.path.exists(output_file) else None,
                error_detail=error_detail,
            )

        except Exception as e:
            error_msg = f"Error executing OpenCode: {e}"
            _DEFAULT_LOGGER.error(error_msg)
            return AgentExecuteResponse(
                output=error_msg,
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=str(e),
            )
