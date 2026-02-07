"""Claude Code provider implementation.

This module extracts all Claude Code-specific logic from the original agent.py
into a dedicated provider implementation. It handles CLI invocation, JSONL
parsing, subprocess management, and streaming output.
"""

import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from rouge.core.agents.base import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    CodingAgent,
)

from .claude_models import ClaudeAgentPromptResponse, ClaudeAgentTemplateRequest

# Load environment variables
load_dotenv()

# Get Claude Code CLI path from environment
CLAUDE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

# Default timeout for Claude CLI operations (10 minutes)
# Claude Code can take significant time for complex tasks
CLAUDE_CLI_TIMEOUT = 600

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


def parse_jsonl_output(
    output_file: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse JSONL output file and return all messages and the result message.

    Returns:
        Tuple of (all_messages, result_message) where result_message is None if not found
    """
    try:
        with open(output_file, "r") as f:
            # Read all lines and parse each as JSON
            messages = [json.loads(line) for line in f if line.strip()]

            # Find the result message (should be the last one)
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

    Returns:
        Path to the created JSON file
    """
    # Create JSON filename by replacing .jsonl with .json
    json_file = jsonl_file.replace(".jsonl", ".json")

    # Parse the JSONL file
    messages, _ = parse_jsonl_output(jsonl_file)

    # Write as JSON array
    with open(json_file, "w") as f:
        json.dump(messages, f, indent=2)

    _DEFAULT_LOGGER.debug("Created JSON file: %s", json_file)
    return json_file


def iter_assistant_items(line: str) -> Iterable[Dict[str, Any]]:
    """Yield assistant text/TodoWrite/Task items parsed from a Claude CLI stdout line.

    This function is critical for real-time streaming progress comments.
    It parses JSONL lines and extracts relevant content items from assistant messages.
    """
    stripped = line.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return []

    if parsed.get("type") != "assistant":
        return []

    message = parsed.get("message")
    if not isinstance(message, dict):
        return []

    content_items = message.get("content")
    if not isinstance(content_items, list):
        return []

    selected: List[Dict[str, Any]] = []
    for item in content_items:
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        is_text = item_type == "text"
        is_todo = item_type == "tool_use" and item.get("name") == "TodoWrite"
        is_task = item_type == "tool_use" and item.get("name") == "Task"

        if is_text or is_todo or is_task:
            selected.append(item)
    return selected


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
    handling subprocess execution, JSONL streaming, and result parsing.

    The implementation preserves all original behavior including:
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
        """Execute Claude Code CLI with the given request.

        This method handles the complete lifecycle:
        1. Map AgentExecuteRequest to Claude-specific parameters
        2. Validate CLI is installed
        3. Save prompt for logging
        4. Execute subprocess with threading for streaming
        5. Parse JSONL results
        6. Map back to AgentExecuteResponse

        Args:
            request: Provider-agnostic execution request
            stream_handler: Optional callback for streaming output lines

        Returns:
            Structured response with results and metadata
        """
        try:
            # Map to Claude-specific model
            model = request.provider_options.get("model", request.model or "opus")
            dangerously_skip_permissions = request.provider_options.get(
                "dangerously_skip_permissions", True
            )

            # Determine output file path
            if request.output_path:
                output_file = request.output_path
            else:
                from rouge.core.workflow.shared import get_working_dir

                agents_log_dir = Path(get_working_dir()) / ".rouge" / "agents" / "logs"
                output_dir = agents_log_dir / request.adw_id / request.agent_name
                output_file = str(output_dir / "raw_output.jsonl")

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

            # Create output directory if needed
            output_file_dir = os.path.dirname(output_file)
            if output_file_dir:
                os.makedirs(output_file_dir, exist_ok=True)

            # Build command - always use stream-json format, verbose, and skip permissions
            cmd = [CLAUDE_PATH, "-p", request.prompt]
            cmd.extend(["--model", model])
            cmd.extend(["--output-format", "stream-json"])
            cmd.append("--verbose")
            if dangerously_skip_permissions:
                cmd.append("--dangerously-skip-permissions")

            # Use current environment for subprocess
            env = os.environ.copy()

            # Import here to avoid circular dependency
            from rouge.core.workflow.shared import get_working_dir

            stderr_lines: List[str] = []

            with open(output_file, "w") as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    cwd=get_working_dir(),
                )

                assert process.stdout is not None
                assert process.stderr is not None
                stdout_pipe = process.stdout
                stderr_pipe = process.stderr

                def _stream_stdout() -> None:
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
                    for line in stderr_pipe:
                        stderr_lines.append(line)
                    stderr_pipe.close()

                stdout_thread = threading.Thread(target=_stream_stdout, daemon=True)
                stderr_thread = threading.Thread(target=_capture_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                process.wait()

                stdout_thread.join()
                stderr_thread.join()

            returncode = process.returncode or 0
            stderr_output = "".join(stderr_lines)

            # Parse results
            messages: List[Dict[str, Any]] = []
            result_message: Optional[Dict[str, Any]] = None
            if os.path.exists(output_file):
                messages, result_message = parse_jsonl_output(output_file)
                convert_jsonl_to_json(output_file)

                # Fallback: pick the last message with result/session_id if parser
                # did not classify it (helps during mocked tests)
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

                if messages:
                    return AgentExecuteResponse(
                        output=json.dumps(messages[-1]),
                        success=True,
                        session_id=None,
                        raw_output_path=output_file,
                        error_detail=None,
                    )

                with open(output_file, "r") as f:
                    raw_output = f.read()
                return AgentExecuteResponse(
                    output=raw_output,
                    success=True,
                    session_id=None,
                    raw_output_path=output_file,
                    error_detail=None,
                )

            # Handle error case
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

            error_msg = f"Claude Code error: {error_detail}"
            return AgentExecuteResponse(
                output=error_msg,
                success=False,
                session_id=session_id,
                raw_output_path=output_file if os.path.exists(output_file) else None,
                error_detail=error_detail,
            )

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


def execute_claude_template(
    request: ClaudeAgentTemplateRequest,
    stream_handler: Optional[Callable[[str], None]] = None,  # noqa: ARG001
) -> ClaudeAgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments.

    This function executes Claude Code CLI with static JSON output format
    and structured output via json_schema when provided.

    Note: stream_handler is ignored in this implementation because Claude Code
    is invoked with --output-format json, which returns a single JSON envelope
    at completion rather than streaming JSONL output. The parameter is kept
    for backward compatibility with ClaudeAgentTemplateRequest callers that
    may pass make_progress_comment_handler or similar streaming callbacks.
    For actual streaming support, the caller should use execute_prompt with
    a provider that supports line-by-line JSONL output.

    Args:
        request: Claude-specific template request
        stream_handler: Optional callback for streaming output (not invoked;
            kept for backward compatibility with existing callers)

    Returns:
        Claude-specific prompt response with structured_output content
    """
    # Construct prompt from slash command and args
    prompt = f"{request.slash_command} {' '.join(request.args)}"

    # Create output directory with adw_id using get_working_dir() as base
    from rouge.core.workflow.shared import get_working_dir

    agents_log_dir = Path(get_working_dir()) / ".rouge" / "agents" / "logs"
    output_dir = agents_log_dir / request.adw_id / request.agent_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build output file path (JSON format, not JSONL)
    output_file = str(output_dir / "raw_output.json")

    # Check if Claude Code CLI is installed
    error_msg = check_claude_installed()
    if error_msg:
        return ClaudeAgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
        )

    # Save prompt before execution
    save_prompt(prompt, request.adw_id, request.agent_name)

    # Build command with JSON output format
    cmd = [CLAUDE_PATH, "-p", prompt]
    cmd.extend(["--model", request.model])
    cmd.extend(["--output-format", "json"])
    cmd.append("--verbose")
    cmd.append("--dangerously-skip-permissions")

    # Append json_schema flag if provided
    if request.json_schema:
        cmd.extend(["--json-schema", request.json_schema])

    # Use current environment for subprocess
    env = os.environ.copy()

    try:
        # Execute subprocess and capture output directly
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=get_working_dir(),
            timeout=CLAUDE_CLI_TIMEOUT,
        )

        # Write raw output to file for logging
        with open(output_file, "w") as f:
            f.write(result.stdout)

        # Parse JSON envelope
        if result.returncode != 0:
            error_detail = (
                result.stderr.strip()
                if result.stderr
                else f"Process exited with code {result.returncode}"
            )
            _DEFAULT_LOGGER.error("Claude Code execution failed: %s", error_detail)
            return ClaudeAgentPromptResponse(
                output=f"Claude Code error: {error_detail}",
                success=False,
                session_id=None,
            )

        # Load and validate JSON envelope
        try:
            envelope = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            _DEFAULT_LOGGER.error("Failed to parse JSON output: %s", e)
            return ClaudeAgentPromptResponse(
                output=f"Failed to parse JSON output: {e}",
                success=False,
                session_id=None,
            )

        # Validate envelope structure
        # Hard checks: type == "result", is_error == false, structured_output is dict
        envelope_type = envelope.get("type")
        is_error = envelope.get("is_error", False)
        structured_output = envelope.get("structured_output")
        session_id = envelope.get("session_id")

        if envelope_type != "result":
            _DEFAULT_LOGGER.error(
                "Invalid envelope type: expected 'result', got '%s'", envelope_type
            )
            return ClaudeAgentPromptResponse(
                output=f"Invalid envelope type: expected 'result', got '{envelope_type}'",
                success=False,
                session_id=session_id,
            )

        if is_error:
            error_result = envelope.get("result", "Unknown error")
            _DEFAULT_LOGGER.error("Claude Code returned error: %s", error_result)
            return ClaudeAgentPromptResponse(
                output=f"Claude Code error: {error_result}",
                success=False,
                session_id=session_id,
            )

        if not isinstance(structured_output, dict):
            got_type = type(structured_output).__name__ if structured_output is not None else "None"
            _DEFAULT_LOGGER.error("Invalid structured_output: expected dict, got %s", got_type)
            return ClaudeAgentPromptResponse(
                output=f"Invalid structured_output: expected dict, got {got_type}",
                success=False,
                session_id=session_id,
            )

        # Soft check: log warning if subtype exists and is not "success"
        subtype = envelope.get("subtype")
        if subtype is not None and subtype != "success":
            _DEFAULT_LOGGER.warning("Envelope subtype is '%s', expected 'success'", subtype)

        # Return structured_output content as output
        return ClaudeAgentPromptResponse(
            output=json.dumps(structured_output),
            success=True,
            session_id=session_id,
        )

    except subprocess.TimeoutExpired as e:
        error_msg = f"Claude CLI timed out after {CLAUDE_CLI_TIMEOUT} seconds: {e.cmd}"
        _DEFAULT_LOGGER.error(error_msg)
        return ClaudeAgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
        )
    except Exception as e:
        error_msg = f"Error executing Claude Code: {e}"
        _DEFAULT_LOGGER.exception(error_msg)
        return ClaudeAgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
        )
