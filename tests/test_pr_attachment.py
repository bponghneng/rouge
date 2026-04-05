"""Tests for the PR attachment rendering helper.

Covers:
- Rendering with both spec and plan present
- Rendering with spec only
- Rendering with plan only
- Returning None when neither is provided
- Collapsible ``<details>`` sections in output
- Plan summary appearing as visible text
- Truncation when content exceeds ~60K chars
- load_and_render_attachment integration with WorkflowContext
"""

from unittest.mock import MagicMock

import pytest

from rouge.core.workflow.step_utils import (
    _MAX_BODY_CHARS,
    _TRUNCATION_NOTICE,
    load_and_render_attachment,
    render_attachment_markdown,
)
from rouge.core.workflow.types import PlanData


class TestRenderAttachmentMarkdown:
    """Unit tests for render_attachment_markdown."""

    def test_render_with_both_spec_and_plan(self) -> None:
        """Both spec and plan sections appear in the rendered output."""
        result = render_attachment_markdown(
            spec_text="My specification",
            plan_text="My plan body",
            plan_summary="Short summary",
        )

        assert result is not None
        assert "Source Specification" in result
        assert "My specification" in result
        assert "Implementation Plan" in result
        assert "My plan body" in result

    def test_render_with_spec_only(self) -> None:
        """Plan section is absent when plan_text is empty."""
        result = render_attachment_markdown(
            spec_text="Only spec here",
            plan_text=None,
            plan_summary=None,
        )

        assert result is not None
        assert "Source Specification" in result
        assert "Only spec here" in result
        assert "Implementation Plan" not in result

    def test_render_with_plan_only(self) -> None:
        """Spec section is absent when spec_text is empty."""
        result = render_attachment_markdown(
            spec_text=None,
            plan_text="Only plan here",
            plan_summary=None,
        )

        assert result is not None
        assert "Source Specification" not in result
        assert "Implementation Plan" in result
        assert "Only plan here" in result

    def test_render_with_neither(self) -> None:
        """Returns None when both spec and plan are absent."""
        result = render_attachment_markdown(
            spec_text=None,
            plan_text=None,
            plan_summary=None,
        )

        assert result is None

    @pytest.mark.parametrize(
        "spec_text,plan_text",
        [
            ("", ""),
            ("   ", "   "),
            ("", None),
            (None, ""),
        ],
    )
    def test_render_with_neither_whitespace_variants(
        self, spec_text: str | None, plan_text: str | None
    ) -> None:
        """Returns None for whitespace-only or empty strings too."""
        result = render_attachment_markdown(
            spec_text=spec_text,
            plan_text=plan_text,
            plan_summary=None,
        )

        assert result is None

    def test_collapsible_sections(self) -> None:
        """Output contains <details> tags for collapsible sections."""
        result = render_attachment_markdown(
            spec_text="spec content",
            plan_text="plan content",
            plan_summary="summary",
        )

        assert result is not None
        assert result.count("<details>") == 2
        assert result.count("</details>") == 2
        assert "<summary>Source Specification</summary>" in result
        assert "<summary>Implementation Plan</summary>" in result

    def test_plan_summary_included(self) -> None:
        """Plan summary appears as visible bold text inside the plan section."""
        result = render_attachment_markdown(
            spec_text="spec",
            plan_text="plan",
            plan_summary="My short summary",
        )

        assert result is not None
        assert "**Summary:** My short summary" in result

    def test_plan_summary_omitted_when_empty(self) -> None:
        """No summary line when plan_summary is None or whitespace."""
        result = render_attachment_markdown(
            spec_text=None,
            plan_text="plan body",
            plan_summary=None,
        )

        assert result is not None
        assert "**Summary:**" not in result

        result_ws = render_attachment_markdown(
            spec_text=None,
            plan_text="plan body",
            plan_summary="   ",
        )

        assert result_ws is not None
        assert "**Summary:**" not in result_ws

    def test_truncation_when_content_exceeds_limit(self) -> None:
        """Body is truncated with a notice when it exceeds _MAX_BODY_CHARS."""
        large_spec = "x" * (_MAX_BODY_CHARS + 5_000)

        result = render_attachment_markdown(
            spec_text=large_spec,
            plan_text=None,
            plan_summary=None,
        )

        assert result is not None
        assert result.endswith(_TRUNCATION_NOTICE)
        # Any <details> tags opened in the truncated portion must be closed before the notice
        body_before_notice = result[: -len(_TRUNCATION_NOTICE)]
        assert body_before_notice.count("<details>") == body_before_notice.count("</details>")

    def test_no_truncation_within_limit(self) -> None:
        """Body is not truncated when within the character limit."""
        result = render_attachment_markdown(
            spec_text="short spec",
            plan_text="short plan",
            plan_summary="summary",
        )

        assert result is not None
        assert _TRUNCATION_NOTICE not in result
        assert result.endswith("*Generated by Rouge*\n")

    def test_footer_present(self) -> None:
        """Output ends with the standard Rouge footer."""
        result = render_attachment_markdown(
            spec_text="spec",
            plan_text=None,
            plan_summary=None,
        )

        assert result is not None
        assert "*Generated by Rouge*" in result


def _make_context(data: dict | None = None) -> MagicMock:
    """Build a mock WorkflowContext with the given data cache.

    The mock's ``load_optional_artifact`` delegates to a simplified version
    of the real method: it checks ``context.data`` for a cached value and,
    if absent, calls the artifact store's ``read_artifact`` (which can be
    configured to raise ``FileNotFoundError``).
    """
    ctx = MagicMock()
    ctx.data = data if data is not None else {}

    def _load_optional(
        context_key: str,
        _artifact_type: str,
        _artifact_class: type,
        extract_fn: object,
    ) -> object:
        existing = ctx.data.get(context_key)
        if existing is not None:
            return existing
        # Simulate artifact store read
        try:
            artifact = ctx.artifact_store.read_artifact(_artifact_type, _artifact_class)
        except FileNotFoundError:
            return None
        value = extract_fn(artifact)  # type: ignore[operator]
        ctx.data[context_key] = value
        return value

    ctx.load_optional_artifact.side_effect = _load_optional
    return ctx


class TestLoadAndRenderAttachment:
    """Integration tests for load_and_render_attachment (artifact loading + rendering)."""

    def test_plan_data_model_in_cache(self) -> None:
        """PlanData model in context cache is rendered correctly (reproduces the bug fix)."""
        plan = PlanData(plan="Implement feature X step by step", summary="Feature X plan")
        ctx = _make_context({"plan_data": plan})
        # No issue artifact in cache; store raises FileNotFoundError
        ctx.artifact_store.read_artifact.side_effect = FileNotFoundError

        result = load_and_render_attachment(ctx)

        assert result is not None
        assert "Implementation Plan" in result
        assert "Implement feature X step by step" in result
        assert "**Summary:** Feature X plan" in result
        # No spec section expected
        assert "Source Specification" not in result

    def test_both_issue_and_plan_in_cache(self) -> None:
        """Both issue data dict and PlanData model produce full output."""
        plan = PlanData(plan="The plan body", summary="Short summary")
        ctx = _make_context(
            {
                "issue_data": {"description": "The spec text"},
                "plan_data": plan,
            }
        )

        result = load_and_render_attachment(ctx)

        assert result is not None
        assert "Source Specification" in result
        assert "The spec text" in result
        assert "Implementation Plan" in result
        assert "The plan body" in result
        assert "**Summary:** Short summary" in result

    def test_only_issue_data_from_store(self) -> None:
        """Output contains spec but no plan when only FetchIssueArtifact is available."""
        from rouge.core.models import Issue
        from rouge.core.workflow.artifacts import FetchIssueArtifact

        issue = Issue(id=1, description="Spec from issue")
        fetch_artifact = FetchIssueArtifact(
            workflow_id="wf-1",
            issue=issue,
        )

        ctx = _make_context()

        def _read_artifact(artifact_type: str, artifact_class: type) -> FetchIssueArtifact:
            if artifact_type == "fetch-issue":
                return fetch_artifact
            raise FileNotFoundError

        ctx.artifact_store.read_artifact.side_effect = _read_artifact

        result = load_and_render_attachment(ctx)

        assert result is not None
        assert "Source Specification" in result
        assert "Spec from issue" in result
        assert "Implementation Plan" not in result

    def test_only_plan_data_in_cache_no_issue(self) -> None:
        """Output contains plan but no spec when only plan_data is cached."""
        plan = PlanData(plan="Only plan content", summary="Plan only summary")
        ctx = _make_context({"plan_data": plan})
        ctx.artifact_store.read_artifact.side_effect = FileNotFoundError

        result = load_and_render_attachment(ctx)

        assert result is not None
        assert "Implementation Plan" in result
        assert "Only plan content" in result
        assert "Source Specification" not in result

    def test_neither_artifact_present(self) -> None:
        """Returns None when both artifact loads return None."""
        ctx = _make_context()
        ctx.artifact_store.read_artifact.side_effect = FileNotFoundError

        result = load_and_render_attachment(ctx)

        assert result is None
