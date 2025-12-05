"""Provider-agnostic coding agent interfaces.

This module defines the abstract base classes and models for integrating
multiple coding agent providers (Claude Code, Aider, Cursor, etc.) with Cape.

The abstraction separates execution logic from notification/progress tracking
by using injectable stream handlers, allowing clean provider implementations
focused solely on execution mechanics.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field


class AgentExecuteRequest(BaseModel):
    """Provider-agnostic agent execution request.

    This model contains all necessary information for executing an agent
    prompt across different provider implementations.

    Attributes:
        prompt: The full prompt/command to execute
        issue_id: Cape issue ID for workflow tracking
        adw_id: Workflow identifier for logging/artifacts
        agent_name: Agent name for directory structure (e.g., "sdlc_implementor")
        model: Optional provider-neutral model name
        output_path: Optional raw output destination path
        provider_options: Provider-specific configuration options
    """

    prompt: str
    issue_id: int
    adw_id: str
    agent_name: str
    model: Optional[str] = None
    output_path: Optional[str] = None
    provider_options: Dict[str, Any] = Field(default_factory=dict)


class AgentExecuteResponse(BaseModel):
    """Provider-agnostic agent execution response.

    This model standardizes the results returned by agent providers,
    regardless of their underlying implementation details.

    Attributes:
        output: Main textual result from execution
        success: Execution success flag
        session_id: Session identifier if available (provider-specific)
        raw_output_path: Path to raw output file if saved
        error_detail: Error message if execution failed
    """

    output: str
    success: bool
    session_id: Optional[str] = None
    raw_output_path: Optional[str] = None
    error_detail: Optional[str] = None


class CodingAgent(ABC):
    """Abstract base class for coding agent providers.

    Implementations must provide the execute_prompt method which handles
    the full execution lifecycle including:
    - Validating prerequisites (CLI availability, credentials, etc.)
    - Running the agent subprocess or API call
    - Streaming output through the optional handler
    - Parsing results into standardized response format
    - Handling errors gracefully

    Stream Handler Protocol:
        If provided, the stream_handler receives raw streaming output
        (typically line-by-line for CLI tools) as execution progresses.
        Handlers should:
        - Parse/process each chunk independently
        - Handle parsing errors gracefully (log and continue)
        - Never raise exceptions (would interrupt execution)
        - Be thread-safe if provider uses threading

    Example:
        def my_handler(line: str) -> None:
            try:
                data = json.loads(line)
                # Process data...
            except Exception as e:
                logger.error(f"Handler error: {e}")
                # Continue - don't raise
    """

    @abstractmethod
    def execute_prompt(
        self,
        request: AgentExecuteRequest,
        *,
        stream_handler: Optional[Callable[[str], None]] = None,
    ) -> AgentExecuteResponse:
        """Execute an agent prompt with optional streaming.

        Args:
            request: Execution parameters including prompt, IDs, and options
            stream_handler: Optional callback receiving raw streaming output.
                          Called for each chunk (typically line) as it arrives.
                          Should handle all errors internally.

        Returns:
            Structured response with output, success status, and metadata

        Raises:
            May raise provider-specific exceptions for critical failures
            (e.g., missing credentials, invalid configuration), but should
            return error responses for execution failures when possible.
        """
        pass
