"""Provider-agnostic coding agent interfaces.

This module defines the abstract base classes and models for integrating
multiple coding agent providers (Claude Code, Aider, Cursor, etc.) with Rouge.

The abstraction separates execution logic from notification/progress tracking
by using injectable stream handlers, allowing clean provider implementations
focused solely on execution mechanics.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentExecuteRequest(BaseModel):
    """Provider-agnostic agent execution request.

    This model contains all necessary information for executing an agent
    prompt across different provider implementations.

    Attributes:
        prompt: The full prompt/command to execute
        issue_id: Rouge issue ID for workflow tracking
        adw_id: Workflow identifier for logging/artifacts
        agent_name: Agent name for directory structure (e.g., "sdlc_implementor")
        model: Optional provider-neutral model name
        output_path: Optional raw output destination path
        provider_options: Provider-specific configuration options
    """

    prompt: str
    issue_id: Optional[int] = None
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
    - Parsing results into standardized response format
    - Handling errors gracefully

    Note: Progress tracking is handled via Supabase comments rather than
    stream handlers. See rouge.core.notifications for comment insertion.
    """

    @abstractmethod
    def execute_prompt(
        self,
        request: AgentExecuteRequest,
    ) -> AgentExecuteResponse:
        """Execute an agent prompt.

        Args:
            request: Execution parameters including prompt, IDs, and options

        Returns:
            Structured response with output, success status, and metadata

        Raises:
            May raise provider-specific exceptions for critical failures
            (e.g., missing credentials, invalid configuration), but should
            return error responses for execution failures when possible.
        """
        pass
