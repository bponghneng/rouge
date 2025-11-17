"""Claude Code agent module for executing prompts programmatically."""

import json
import logging
import os
import re
import subprocess
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from cape.core.models import (
    AgentPromptRequest,
    AgentPromptResponse,
    AgentTemplateRequest,
)
from cape.core.notifications import insert_progress_comment

# Load environment variables
load_dotenv()

# Get Claude Code CLI path from environment
CLAUDE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

_DEFAULT_LOGGER = logging.getLogger(__name__)


def _get_issue_logger(adw_id: str) -> logging.Logger:
    """Return logger bound to a specific workflow or fall back to module logger."""
    issue_logger = logging.getLogger(f"cape_{adw_id}")
    return issue_logger if issue_logger.handlers else _DEFAULT_LOGGER


def _emit_comment(request: AgentPromptRequest, message: str) -> None:
    """Write a progress comment tied to the request's issue."""
    text = message.strip()
    if not text:
        return
    insert_progress_comment(request.issue_id, text, _get_issue_logger(request.adw_id))


def check_claude_installed() -> Optional[str]:
    """Check if Claude Code CLI is installed. Return error message if not."""
    try:
        result = subprocess.run([CLAUDE_PATH, "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    except FileNotFoundError:
        return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    return None


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
    """Yield assistant text/TodoWrite items parsed from a Claude CLI stdout line."""
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

        if is_text or is_todo:
            selected.append(item)
    return selected


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

    # Create directory structure using current working directory or env override
    agents_dir = os.environ.get("CAPE_AGENTS_DIR", os.path.join(os.getcwd(), ".cape/logs/agents"))
    prompt_dir = os.path.join(agents_dir, adw_id, agent_name, "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    # Save prompt to file
    prompt_file = os.path.join(prompt_dir, f"{command_name}.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)

    _DEFAULT_LOGGER.debug("Saved prompt to: %s", prompt_file)


def prompt_claude_code(request: AgentPromptRequest) -> AgentPromptResponse:
    """Execute Claude Code with the given prompt configuration."""

    # Check if Claude Code CLI is installed
    error_msg = check_claude_installed()
    if error_msg:
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)

    # Save prompt before execution
    save_prompt(request.prompt, request.adw_id, request.agent_name)

    # Create output directory if needed
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Build command - always use stream-json format, verbose, and skip permissions
    cmd = [CLAUDE_PATH, "-p", request.prompt]
    cmd.extend(["--model", request.model])
    cmd.extend(["--output-format", "stream-json"])
    cmd.append("--verbose")
    cmd.append("--dangerously-skip-permissions")

    # Ensure we use the locally authenticated Claude CLI (not API key fallback)
    env = os.environ.copy()

    try:
        stderr_lines: List[str] = []

        with open(request.output_file, "w") as f:
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
                for line in stdout_pipe:
                    f.write(line)
                    f.flush()
                    for item in iter_assistant_items(line):
                        _emit_comment(request, json.dumps(item, indent=2))
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

        messages: List[Dict[str, Any]] = []
        result_message: Optional[Dict[str, Any]] = None
        if os.path.exists(request.output_file):
            messages, result_message = parse_jsonl_output(request.output_file)
            convert_jsonl_to_json(request.output_file)

            # Fallback: pick the last message with result/session_id if parser
            # did not classify it (helps during mocked tests)
            if not result_message and messages:
                for message in reversed(messages):
                    if message.get("type") == "result" or message.get("session_id"):
                        result_message = message
                        break

        if returncode == 0:
            _emit_comment(request, f"Output saved to: {request.output_file}")

            if result_message:
                session_id = result_message.get("session_id")
                is_error = result_message.get("is_error", False)
                result_text = result_message.get("result", "")

                return AgentPromptResponse(
                    output=result_text,
                    success=not is_error,
                    session_id=session_id,
                )

            if messages:
                return AgentPromptResponse(
                    output=json.dumps(messages[-1]),
                    success=True,
                    session_id=None,
                )

            with open(request.output_file, "r") as f:
                raw_output = f.read()
            return AgentPromptResponse(output=raw_output, success=True, session_id=None)

        error_detail = stderr_output.strip()
        if result_message:
            session_id = result_message.get("session_id")
            result_text = result_message.get("result", "").strip()
            if result_text:
                error_detail = result_text
        elif messages:
            last_message = messages[-1]
            error_detail = (
                last_message.get("result") or last_message.get("error") or json.dumps(last_message)
            )
        elif os.path.exists(request.output_file):
            with open(request.output_file, "r") as f:
                error_detail = f.read().strip() or error_detail

        if not error_detail:
            error_detail = f"Process exited with code {returncode}"

        error_msg = f"Claude Code error: {error_detail}"
        _emit_comment(request, error_msg)
        session_id = result_message.get("session_id") if result_message else None
        return AgentPromptResponse(output=error_msg, success=False, session_id=session_id)

    except Exception as e:
        error_msg = f"Error executing Claude Code: {e}"
        _emit_comment(request, error_msg)
        return AgentPromptResponse(output=error_msg, success=False, session_id=None)


def execute_template(request: AgentTemplateRequest) -> AgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments."""
    # Construct prompt from slash command and args
    prompt = f"{request.slash_command} {' '.join(request.args)}"

    # Create output directory with adw_id using current working directory
    agents_dir = os.environ.get("CAPE_AGENTS_DIR", os.path.join(os.getcwd(), ".cape/logs/agents"))
    output_dir = os.path.join(agents_dir, request.adw_id, request.agent_name)
    os.makedirs(output_dir, exist_ok=True)

    # Build output file path
    output_file = os.path.join(output_dir, "raw_output.jsonl")

    # Create prompt request with specific parameters
    prompt_request = AgentPromptRequest(
        prompt=prompt,
        adw_id=request.adw_id,
        issue_id=request.issue_id,
        agent_name=request.agent_name,
        model=request.model,
        dangerously_skip_permissions=True,
        output_file=output_file,
    )

    # Execute and return response (prompt_claude_code now handles all parsing)
    return prompt_claude_code(prompt_request)
