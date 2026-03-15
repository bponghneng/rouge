"""Prompt registry: loads, parses, and renders packaged workflow templates.

Templates are stored as Markdown files with optional YAML front matter under
``rouge/core/prompts/templates/``. The front matter allowlist is intentionally
narrow: only ``model`` and ``description`` are extracted; ``thinking`` and any
other keys are silently ignored.

Variable substitution uses the ``$ARGUMENTS`` convention: the renderer joins
the provided args list with a newline and replaces the first occurrence of
``$ARGUMENTS`` in the template body.
"""

from __future__ import annotations

import importlib.resources
import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from rouge.core.prompts.prompt_id import PromptId

logger = logging.getLogger(__name__)

# Front matter keys that Rouge maps to structured metadata.
# All other keys are silently dropped.
_ALLOWED_FRONT_MATTER_KEYS = {"description", "model"}

_VALID_MODELS = {"sonnet", "opus", "haiku"}


@dataclass
class PromptTemplate:
    """A loaded and parsed prompt template.

    Attributes:
        prompt_id: The identifier for this template.
        body: Template body text (front matter stripped).
        description: Optional human-readable description from front matter.
        model: Optional model hint from front matter ("sonnet", "opus", or "haiku").
    """

    prompt_id: PromptId
    body: str
    description: Optional[str] = None
    model: Optional[Literal["sonnet", "opus", "haiku"]] = None


@dataclass
class RenderedPrompt:
    """A fully rendered prompt ready for provider execution.

    Attributes:
        text: The rendered prompt text with arguments substituted.
        model: Optional model hint from the template front matter.
    """

    text: str
    model: Optional[Literal["sonnet", "opus", "haiku"]] = None


class PromptRegistry:
    """Loads and caches packaged prompt templates.

    Templates are discovered from the ``rouge.core.prompts.templates``
    package path at first access and cached for the lifetime of the registry.
    """

    def __init__(self) -> None:
        self._cache: Dict[PromptId, PromptTemplate] = {}

    def get(self, prompt_id: PromptId) -> PromptTemplate:
        """Return the parsed template for *prompt_id*.

        Raises:
            FileNotFoundError: If the template file does not exist.
            ValueError: If the template cannot be parsed.
        """
        if prompt_id not in self._cache:
            self._cache[prompt_id] = self._load(prompt_id)
        return self._cache[prompt_id]

    def _load(self, prompt_id: PromptId) -> PromptTemplate:
        """Read and parse a single template from packaged resources."""
        filename = f"{prompt_id.value}.md"
        try:
            package = importlib.resources.files("rouge.core.prompts.templates")
            text = (package / filename).read_text(encoding="utf-8")
        except (FileNotFoundError, TypeError) as exc:
            raise FileNotFoundError(f"Prompt template not found: {filename}") from exc

        description, model, body = _parse_template(text, prompt_id)
        if not body.strip():
            raise ValueError(f"Prompt template {filename} has an empty body")
        return PromptTemplate(
            prompt_id=prompt_id,
            body=body,
            description=description,
            model=model,
        )

    def validate(self) -> None:
        """Eagerly load and validate all known prompt templates.

        Raises:
            FileNotFoundError: If any template file is missing.
            ValueError: If any template body is empty.
        """
        for prompt_id in PromptId:
            self.get(prompt_id)

    def render(self, prompt_id: PromptId, args: List[str]) -> RenderedPrompt:
        """Render *prompt_id* by substituting *args* for ``$ARGUMENTS``.

        If the template body does not contain ``$ARGUMENTS``, the joined args
        are appended at the end so the provider always receives the full input.

        Args:
            prompt_id: The prompt to render.
            args: Positional arguments; joined with ``\\n`` for substitution.

        Returns:
            RenderedPrompt with substituted text and optional model hint.
        """
        template = self.get(prompt_id)
        joined = "\n".join(args)
        if "$ARGUMENTS" in template.body:
            text = template.body.replace("$ARGUMENTS", joined, 1)
        else:
            text = template.body + ("\n\n" + joined if joined else "")
        return RenderedPrompt(text=text, model=template.model)


def _parse_template(
    text: str, prompt_id: PromptId
) -> tuple[Optional[str], Optional[Literal["sonnet", "opus", "haiku"]], str]:
    """Parse YAML front matter from *text* using the narrow allowlist.

    Returns:
        (description, model, body) where body is the text after front matter.
    """
    description: Optional[str] = None
    model: Optional[Literal["sonnet", "opus", "haiku"]] = None

    if not text.startswith("---"):
        return description, model, text

    end = text.find("\n---", 3)
    if end == -1:
        return description, model, text

    front_matter_block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")

    for line in front_matter_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key not in _ALLOWED_FRONT_MATTER_KEYS:
            continue

        if key == "description":
            description = value
        elif key == "model":
            if value in _VALID_MODELS:
                model = value  # type: ignore[assignment]
            else:
                logger.warning(
                    "Prompt %s: unsupported model %r in front matter, ignoring",
                    prompt_id.value,
                    value,
                )

    return description, model, body


# Module-level singleton registry and its creation lock.
_registry: Optional[PromptRegistry] = None
_registry_lock: threading.Lock = threading.Lock()


def get_registry() -> PromptRegistry:
    """Return the shared module-level PromptRegistry instance.

    On first call, eagerly validates all packaged templates so that missing
    or empty templates are caught at startup rather than mid-workflow.

    Thread-safe: guarded by a module-level lock so concurrent callers in a
    thread-pool environment cannot create duplicate registry instances.

    Raises:
        FileNotFoundError: If any template file is missing from the package.
        ValueError: If any template body is empty.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                reg = PromptRegistry()
                reg.validate()
                _registry = reg
    return _registry


def render_prompt(prompt_id: PromptId, args: List[str]) -> RenderedPrompt:
    """Convenience wrapper: render *prompt_id* using the shared registry."""
    return get_registry().render(prompt_id, args)
