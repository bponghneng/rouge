"""End-to-end tests for ``post_glab_attachment_note`` pagination behavior.

These tests drive ``post_glab_attachment_note`` with a patched
``subprocess.run`` and assert on the observed call sequence. They exercise the
private ``_find_existing_glab_marker_note_id`` helper indirectly so the public
contract stays the test surface.
"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.workflow.step_utils import (
    _REVIEW_CONTEXT_MARKER,
    post_glab_attachment_note,
)

_LOGGER_NAME = "rouge.core.workflow.step_utils"
_REPO_PATH = "/tmp/fake-repo"
_MR_NUMBER = 42
_BODY = "rendered body"
_ENV = {"GITLAB_TOKEN": "fake"}


def _make_note(note_id: int, *, marker: bool = False) -> dict:
    body = (
        f"{_REVIEW_CONTEXT_MARKER}\nold content" if marker else f"some unrelated comment {note_id}"
    )
    return {"id": note_id, "body": body}


def _ok(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


def _classify(cmd: list[str]) -> str:
    """Return a short tag describing which subprocess branch was invoked."""
    cmd_str = " ".join(cmd)
    if "api" in cmd_str and "notes?page=1" in cmd_str:
        return "list_page_1"
    if "api" in cmd_str and "notes?page=2" in cmd_str:
        return "list_page_2"
    if "api" in cmd_str and "PUT" in cmd_str:
        return "put_update"
    if "mr" in cmd_str and "note" in cmd_str:
        return "create_note"
    return "unknown"


def _build_side_effect(page_responses: dict[str, MagicMock]):
    """Return a side_effect that maps classified calls to canned responses."""

    def _side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
        tag = _classify(cmd)
        if tag in page_responses:
            response = page_responses[tag]
            if isinstance(response, Exception):
                raise response
            return response
        # Default: PUT and create both succeed.
        if tag == "put_update":
            return _ok()
        if tag == "create_note":
            return _ok()
        return _ok()

    return _side_effect


def _calls_by_tag(mock_run: MagicMock) -> dict[str, list[list[str]]]:
    """Group recorded subprocess.run call commands by classification tag."""
    grouped: dict[str, list[list[str]]] = {}
    for call in mock_run.call_args_list:
        cmd = call.args[0] if call.args else call.kwargs.get("args")
        tag = _classify(cmd)
        grouped.setdefault(tag, []).append(cmd)
    return grouped


def test_first_page_match_triggers_update() -> None:
    page_1_notes = [_make_note(i) for i in range(1, 51)]
    page_1_notes[4] = _make_note(500, marker=True)  # 5th note carries marker
    side_effect = _build_side_effect({"list_page_1": _ok(json.dumps(page_1_notes))})

    with patch(
        "rouge.core.workflow.step_utils.subprocess.run", side_effect=side_effect
    ) as mock_run:
        post_glab_attachment_note(_REPO_PATH, _MR_NUMBER, _BODY, _ENV)

    grouped = _calls_by_tag(mock_run)
    assert len(grouped.get("list_page_1", [])) == 1
    assert "list_page_2" not in grouped
    assert len(grouped.get("put_update", [])) == 1
    assert "create_note" not in grouped
    put_cmd = grouped["put_update"][0]
    assert any("notes/500" in part for part in put_cmd)


def test_second_page_match_triggers_update() -> None:
    page_1_notes = [_make_note(i) for i in range(1, 101)]
    page_2_notes = [_make_note(i) for i in range(101, 131)]
    page_2_notes[10] = _make_note(777, marker=True)
    side_effect = _build_side_effect(
        {
            "list_page_1": _ok(json.dumps(page_1_notes)),
            "list_page_2": _ok(json.dumps(page_2_notes)),
        }
    )

    with patch(
        "rouge.core.workflow.step_utils.subprocess.run", side_effect=side_effect
    ) as mock_run:
        post_glab_attachment_note(_REPO_PATH, _MR_NUMBER, _BODY, _ENV)

    grouped = _calls_by_tag(mock_run)
    assert len(grouped.get("list_page_1", [])) == 1
    assert len(grouped.get("list_page_2", [])) == 1
    assert len(grouped.get("put_update", [])) == 1
    assert "create_note" not in grouped
    put_cmd = grouped["put_update"][0]
    assert any("notes/777" in part for part in put_cmd)


def test_no_match_creates_note() -> None:
    page_1_notes = [_make_note(i) for i in range(1, 101)]
    page_2_notes = [_make_note(i) for i in range(101, 151)]
    side_effect = _build_side_effect(
        {
            "list_page_1": _ok(json.dumps(page_1_notes)),
            "list_page_2": _ok(json.dumps(page_2_notes)),
        }
    )

    with patch(
        "rouge.core.workflow.step_utils.subprocess.run", side_effect=side_effect
    ) as mock_run:
        post_glab_attachment_note(_REPO_PATH, _MR_NUMBER, _BODY, _ENV)

    grouped = _calls_by_tag(mock_run)
    assert len(grouped.get("list_page_1", [])) == 1
    assert len(grouped.get("list_page_2", [])) == 1
    assert "put_update" not in grouped
    assert len(grouped.get("create_note", [])) == 1
    create_cmd = grouped["create_note"][0]
    # Marker should appear in the create message body.
    assert any(_REVIEW_CONTEXT_MARKER in part for part in create_cmd)


def test_list_failure_falls_back_to_create(caplog: pytest.LogCaptureFixture) -> None:
    failed = MagicMock()
    failed.returncode = 1
    failed.stdout = ""
    failed.stderr = "boom: gitlab unavailable"
    side_effect = _build_side_effect({"list_page_1": failed})

    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    with patch(
        "rouge.core.workflow.step_utils.subprocess.run", side_effect=side_effect
    ) as mock_run:
        post_glab_attachment_note(_REPO_PATH, _MR_NUMBER, _BODY, _ENV)

    grouped = _calls_by_tag(mock_run)
    assert len(grouped.get("list_page_1", [])) == 1
    assert "list_page_2" not in grouped
    assert "put_update" not in grouped
    assert len(grouped.get("create_note", [])) == 1
    # Warning should mention the page that failed.
    warning_messages = [
        rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING
    ]
    assert any("page=1" in msg for msg in warning_messages)


def test_malformed_json_falls_back_to_create(caplog: pytest.LogCaptureFixture) -> None:
    side_effect = _build_side_effect({"list_page_1": _ok("not json")})

    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)
    with patch(
        "rouge.core.workflow.step_utils.subprocess.run", side_effect=side_effect
    ) as mock_run:
        post_glab_attachment_note(_REPO_PATH, _MR_NUMBER, _BODY, _ENV)

    grouped = _calls_by_tag(mock_run)
    assert len(grouped.get("list_page_1", [])) == 1
    assert "list_page_2" not in grouped
    assert "put_update" not in grouped
    assert len(grouped.get("create_note", [])) == 1
    warning_messages = [
        rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING
    ]
    assert any("Malformed" in msg for msg in warning_messages)
