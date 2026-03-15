"""Tests for the Rouge prompt registry system.

Covers:
- PromptId enum correctness
- Front matter parsing (allowlist, invalid model, unknown keys, thinking dropped)
- PromptRegistry loading, caching, and rendering
- Contract: every PromptId resolves to a real packaged template
- Module-level helpers (get_registry singleton, render_prompt)
"""

import importlib.resources
from unittest.mock import patch

import pytest

from rouge.core.prompts import PromptId, PromptRegistry, get_registry, render_prompt
from rouge.core.prompts.registry import (
    PromptTemplate,
    RenderedPrompt,
    _parse_template,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_fake_package(files: dict[str, str]) -> object:
    """Return a fake importlib.resources package with the given file contents."""

    class _FakeResource:
        def __init__(self, name: str, content: str):
            self.name = name
            self._content = content

        def read_text(self, encoding="utf-8"):
            return self._content

        def __truediv__(self, name):
            if name in {r.name for r in _resources}:
                return next(r for r in _resources if r.name == name)
            raise FileNotFoundError(name)

    class _FakePackage:
        def __truediv__(self, name):
            if name in files:
                return _FakeResource(name, files[name])
            raise FileNotFoundError(name)

        def iterdir(self):
            return iter(_resources)

    _resources = [_FakeResource(name, content) for name, content in files.items()]
    return _FakePackage()


# ---------------------------------------------------------------------------
# PromptId
# ---------------------------------------------------------------------------


class TestPromptId:
    """Tests for the PromptId enum."""

    def test_all_expected_members_exist(self) -> None:
        """Every workflow step prompt ID is declared."""
        expected = {
            "ACCEPTANCE",
            "BUG_PLAN",
            "CHORE_PLAN",
            "CLASSIFY",
            "CLAUDE_CODE_PLAN",
            "CODE_QUALITY",
            "CODE_REVIEW_SUMMARY",
            "COMPOSE_COMMITS",
            "FEATURE_PLAN",
            "IMPLEMENT_PLAN",
            "IMPLEMENT_REVIEW",
            "PATCH_PLAN",
            "PULL_REQUEST",
            "REVIEW_PLAN",
        }
        actual = {m.name for m in PromptId}
        assert actual == expected

    def test_values_have_no_adw_prefix(self) -> None:
        """PromptId values do not carry an 'adw-' prefix."""
        for prompt_id in PromptId:
            assert not prompt_id.value.startswith(
                "adw-"
            ), f"{prompt_id.name} value {prompt_id.value!r} still has 'adw-' prefix"

    def test_is_str_subclass(self) -> None:
        """PromptId inherits from str so it serialises cleanly."""
        assert isinstance(PromptId.CLASSIFY, str)
        assert PromptId.CLASSIFY == "classify"

    def test_specific_values(self) -> None:
        """Spot-check a few value mappings."""
        assert PromptId.CLASSIFY.value == "classify"
        assert PromptId.FEATURE_PLAN.value == "feature-plan"
        assert PromptId.IMPLEMENT_PLAN.value == "implement-plan"
        assert PromptId.REVIEW_PLAN.value == "review-plan"

    def test_count(self) -> None:
        """Exactly 14 prompt IDs are declared."""
        assert len(list(PromptId)) == 14


# ---------------------------------------------------------------------------
# _parse_template
# ---------------------------------------------------------------------------


class TestParseTemplate:
    """Unit tests for _parse_template internal function."""

    def test_no_front_matter_returns_full_text_as_body(self) -> None:
        text = "# My Prompt\n\nDo something."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        assert description is None
        assert model is None
        assert body == text

    def test_extracts_description(self) -> None:
        text = "---\ndescription: Classify an issue.\n---\n\nBody text."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        assert description == "Classify an issue."
        assert model is None
        assert body == "Body text."

    def test_extracts_model_sonnet(self) -> None:
        text = "---\nmodel: sonnet\n---\n\nBody."
        _, model, _ = _parse_template(text, PromptId.CLASSIFY)
        assert model == "sonnet"

    def test_extracts_model_opus(self) -> None:
        text = "---\nmodel: opus\n---\n\nBody."
        _, model, _ = _parse_template(text, PromptId.CLASSIFY)
        assert model == "opus"

    def test_invalid_model_is_ignored(self) -> None:
        text = "---\nmodel: gpt-4\n---\n\nBody."
        _, model, _ = _parse_template(text, PromptId.CLASSIFY)
        assert model is None

    def test_invalid_model_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        text = "---\nmodel: gpt-4\n---\n\nBody."
        with caplog.at_level(logging.WARNING, logger="rouge.core.prompts.registry"):
            _parse_template(text, PromptId.CLASSIFY)
        assert any("unsupported model" in r.message for r in caplog.records)

    def test_thinking_key_is_silently_dropped(self) -> None:
        text = "---\nthinking: extended\ndescription: A prompt.\n---\n\nBody."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        # thinking is not returned; description is still extracted
        assert description == "A prompt."
        assert model is None
        assert "thinking" not in body

    def test_unknown_keys_are_silently_dropped(self) -> None:
        text = "---\nunknown_key: some value\ndescription: Kept.\n---\n\nBody."
        description, _, _ = _parse_template(text, PromptId.CLASSIFY)
        assert description == "Kept."

    def test_both_description_and_model_extracted(self) -> None:
        text = "---\ndescription: Do stuff.\nmodel: opus\n---\n\nBody text here."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        assert description == "Do stuff."
        assert model == "opus"
        assert body == "Body text here."

    def test_body_leading_newlines_stripped(self) -> None:
        text = "---\ndescription: X.\n---\n\n\nBody starts here."
        _, _, body = _parse_template(text, PromptId.CLASSIFY)
        assert body == "Body starts here."

    def test_unclosed_front_matter_returns_full_text(self) -> None:
        text = "---\ndescription: Missing close\nBody text."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        assert description is None
        assert body == text

    def test_empty_front_matter_block(self) -> None:
        text = "---\n---\n\nBody only."
        description, model, body = _parse_template(text, PromptId.CLASSIFY)
        assert description is None
        assert model is None
        assert body == "Body only."

    def test_description_with_colon_in_value(self) -> None:
        """Values containing colons are preserved correctly."""
        text = "---\ndescription: Foo: bar baz.\n---\n\nBody."
        description, _, _ = _parse_template(text, PromptId.CLASSIFY)
        assert description == "Foo: bar baz."


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------


class TestPromptRegistryGet:
    """Tests for PromptRegistry.get()."""

    def test_get_returns_prompt_template(self) -> None:
        registry = PromptRegistry()
        template = registry.get(PromptId.CLASSIFY)
        assert isinstance(template, PromptTemplate)
        assert template.prompt_id == PromptId.CLASSIFY

    def test_get_caches_result(self) -> None:
        registry = PromptRegistry()
        t1 = registry.get(PromptId.CLASSIFY)
        t2 = registry.get(PromptId.CLASSIFY)
        assert t1 is t2

    def test_get_missing_template_raises_file_not_found(self) -> None:
        registry = PromptRegistry()
        with patch.object(registry, "_load", side_effect=FileNotFoundError("missing")):
            with pytest.raises(FileNotFoundError):
                registry.get(PromptId.CLASSIFY)

    def test_empty_body_raises_value_error(self) -> None:
        """_load raises ValueError when the template body is empty after parsing."""
        registry = PromptRegistry()
        with patch(
            "importlib.resources.files",
            return_value=_make_fake_package({"classify.md": "---\ndescription: x\n---\n\n   \n"}),
        ):
            with pytest.raises(ValueError, match="empty body"):
                registry._load(PromptId.CLASSIFY)

    def test_whitespace_only_body_raises_value_error(self) -> None:
        """A template whose body is only whitespace is rejected."""
        registry = PromptRegistry()
        with patch(
            "importlib.resources.files",
            return_value=_make_fake_package({"classify.md": "   \n\t\n"}),
        ):
            with pytest.raises(ValueError, match="empty body"):
                registry._load(PromptId.CLASSIFY)

    def test_template_body_is_non_empty(self) -> None:
        registry = PromptRegistry()
        template = registry.get(PromptId.CLASSIFY)
        assert template.body.strip() != ""

    def test_template_body_has_no_front_matter_markers(self) -> None:
        """Loaded body should not start with '---' (front matter stripped)."""
        registry = PromptRegistry()
        for prompt_id in PromptId:
            template = registry.get(prompt_id)
            assert not template.body.startswith(
                "---"
            ), f"{prompt_id.value} body still contains front matter marker"

    def test_classify_template_has_model_sonnet(self) -> None:
        """classify.md front matter declares model: sonnet."""
        registry = PromptRegistry()
        template = registry.get(PromptId.CLASSIFY)
        assert template.model == "sonnet"

    def test_templates_without_model_return_none(self) -> None:
        """Templates that omit 'model' in front matter return model=None."""
        registry = PromptRegistry()
        # adw-feature-plan has no model key
        template = registry.get(PromptId.FEATURE_PLAN)
        assert template.model is None

    def test_no_template_contains_thinking_key(self) -> None:
        """Confirm 'thinking' was removed from all migrated templates."""
        registry = PromptRegistry()
        for prompt_id in PromptId:
            template = registry.get(prompt_id)
            # body should not contain "thinking:" as a front matter line
            assert "thinking:" not in template.body


class TestPromptRegistryValidate:
    """Tests for PromptRegistry.validate() — eager load-time validation."""

    def test_validate_succeeds_for_all_packaged_templates(self) -> None:
        """validate() loads all PromptIds without raising."""
        registry = PromptRegistry()
        registry.validate()  # must not raise

    def test_validate_populates_entire_cache(self) -> None:
        """After validate(), every PromptId is in the cache."""
        registry = PromptRegistry()
        registry.validate()
        for prompt_id in PromptId:
            assert prompt_id in registry._cache

    def test_validate_raises_if_template_missing(self) -> None:
        """validate() raises FileNotFoundError if any template file is absent."""
        registry = PromptRegistry()
        original_load = registry._load

        def load_with_one_missing(prompt_id):
            if prompt_id == PromptId.CLASSIFY:
                raise FileNotFoundError("classify.md")
            return original_load(prompt_id)

        with patch.object(registry, "_load", side_effect=load_with_one_missing):
            with pytest.raises(FileNotFoundError):
                registry.validate()

    def test_validate_raises_if_template_body_empty(self) -> None:
        """validate() raises ValueError if any template has an empty body."""
        registry = PromptRegistry()
        original_load = registry._load

        def load_with_empty_body(prompt_id):
            if prompt_id == PromptId.CLASSIFY:
                raise ValueError("classify.md has an empty body")
            return original_load(prompt_id)

        with patch.object(registry, "_load", side_effect=load_with_empty_body):
            with pytest.raises(ValueError):
                registry.validate()


class TestPromptRegistryRender:
    """Tests for PromptRegistry.render()."""

    def test_render_substitutes_arguments(self) -> None:
        registry = PromptRegistry()
        result = registry.render(PromptId.CLASSIFY, ["Issue text here"])
        assert isinstance(result, RenderedPrompt)
        assert "Issue text here" in result.text
        assert "$ARGUMENTS" not in result.text

    def test_render_multiple_args_joined_with_newline(self) -> None:
        registry = PromptRegistry()
        result = registry.render(PromptId.CLASSIFY, ["line one", "line two"])
        assert "line one\nline two" in result.text

    def test_render_empty_args_with_arguments_placeholder(self) -> None:
        """$ARGUMENTS replaced with empty string when args=[]."""
        registry = PromptRegistry()
        result = registry.render(PromptId.CLASSIFY, [])
        assert "$ARGUMENTS" not in result.text

    def test_render_no_arguments_placeholder_appends_args(self) -> None:
        """Templates without $ARGUMENTS get args appended."""
        registry = PromptRegistry()
        # adw-code-quality.md has no $ARGUMENTS
        result = registry.render(PromptId.CODE_QUALITY, ["extra context"])
        assert "extra context" in result.text

    def test_render_no_arguments_placeholder_empty_args_no_append(self) -> None:
        """Templates without $ARGUMENTS and empty args produce clean body."""
        registry = PromptRegistry()
        result = registry.render(PromptId.CODE_QUALITY, [])
        # body unchanged, no trailing whitespace artifact
        template = registry.get(PromptId.CODE_QUALITY)
        assert result.text == template.body

    def test_render_returns_model_from_template(self) -> None:
        registry = PromptRegistry()
        result = registry.render(PromptId.CLASSIFY, ["x"])
        assert result.model == "sonnet"

    def test_render_returns_none_model_when_not_in_front_matter(self) -> None:
        registry = PromptRegistry()
        result = registry.render(PromptId.FEATURE_PLAN, ["x"])
        assert result.model is None

    def test_render_only_first_arguments_replaced(self) -> None:
        """Only the first $ARGUMENTS occurrence is substituted."""
        registry = PromptRegistry()
        # Inject a synthetic template with two $ARGUMENTS
        fake_template = PromptTemplate(
            prompt_id=PromptId.CLASSIFY,
            body="First: $ARGUMENTS. Second: $ARGUMENTS.",
            description=None,
            model=None,
        )
        registry._cache[PromptId.CLASSIFY] = fake_template
        result = registry.render(PromptId.CLASSIFY, ["X"])
        assert result.text == "First: X. Second: $ARGUMENTS."


# ---------------------------------------------------------------------------
# Contract: every PromptId resolves to a real packaged template
# ---------------------------------------------------------------------------


class TestPromptIdTemplateContract:
    """Ensure every declared PromptId has a corresponding packaged .md file."""

    @pytest.mark.parametrize("prompt_id", list(PromptId))
    def test_template_file_exists(self, prompt_id: PromptId) -> None:
        """Every PromptId must have a matching template file in the package."""
        filename = f"{prompt_id.value}.md"
        package = importlib.resources.files("rouge.core.prompts.templates")
        resource = package / filename
        # read_text raises FileNotFoundError if missing
        content = resource.read_text(encoding="utf-8")
        assert content.strip() != "", f"Template {filename} is empty"

    @pytest.mark.parametrize("prompt_id", list(PromptId))
    def test_template_loads_via_registry(self, prompt_id: PromptId) -> None:
        """Every PromptId must load cleanly through PromptRegistry."""
        registry = PromptRegistry()
        template = registry.get(prompt_id)
        assert template.prompt_id == prompt_id
        assert template.body.strip() != ""

    @pytest.mark.parametrize("prompt_id", list(PromptId))
    def test_template_renders_without_error(self, prompt_id: PromptId) -> None:
        """Every PromptId must render with sample args without raising."""
        registry = PromptRegistry()
        result = registry.render(prompt_id, ["sample argument"])
        assert isinstance(result, RenderedPrompt)
        assert result.text.strip() != ""

    def test_no_orphan_template_files(self) -> None:
        """Every .md file in the templates package has a matching PromptId."""
        package = importlib.resources.files("rouge.core.prompts.templates")
        declared_values = {p.value for p in PromptId}
        for resource in package.iterdir():
            name = resource.name
            if not name.endswith(".md"):
                continue
            stem = name[: -len(".md")]
            assert stem in declared_values, f"Template file '{name}' has no matching PromptId"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleLevelHelpers:
    """Tests for get_registry() and render_prompt() convenience wrappers."""

    def test_get_registry_returns_prompt_registry(self) -> None:
        registry = get_registry()
        assert isinstance(registry, PromptRegistry)

    def test_get_registry_is_singleton(self) -> None:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_eagerly_validates_all_templates(self) -> None:
        """get_registry() triggers validate() so all templates are cached on first call."""
        import rouge.core.prompts.registry as _mod

        old = _mod._registry
        try:
            _mod._registry = None
            registry = get_registry()
            # All PromptIds must be cached — validation happened at startup
            for prompt_id in PromptId:
                assert (
                    prompt_id in registry._cache
                ), f"{prompt_id.value} was not validated at registry creation"
        finally:
            _mod._registry = old

    def test_render_prompt_returns_rendered_prompt(self) -> None:
        result = render_prompt(PromptId.CLASSIFY, ["test input"])
        assert isinstance(result, RenderedPrompt)
        assert "test input" in result.text

    def test_render_prompt_uses_shared_registry(self) -> None:
        """render_prompt() and get_registry().render() share the same cache."""
        shared = get_registry()
        _ = render_prompt(PromptId.CLASSIFY, ["x"])
        # Cache populated via render_prompt should be visible in the registry
        assert PromptId.CLASSIFY in shared._cache
