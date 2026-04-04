"""Tests for the PR attachment rendering helper.

Covers:
- Rendering with both spec and plan present
- Rendering with spec only
- Rendering with plan only
- Returning None when neither is provided
- Collapsible ``<details>`` sections in output
- Plan summary appearing as visible text
- Truncation when content exceeds ~60K chars
"""

import pytest

from rouge.core.workflow.steps.pr_attachment import (
    _MAX_BODY_CHARS,
    _TRUNCATION_NOTICE,
    render_attachment_markdown,
)


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
        assert len(result) <= _MAX_BODY_CHARS + len(_TRUNCATION_NOTICE)
        assert result.endswith(_TRUNCATION_NOTICE)

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
        assert "---" in result
