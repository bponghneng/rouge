"""Tests for JSON parsing helper module."""

import logging
from unittest.mock import Mock

import pytest

from cape.core.json_parser import _sanitize_json_output, parse_and_validate_json


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return Mock(spec=logging.Logger)


class TestSanitizeJsonOutput:
    """Tests for _sanitize_json_output helper."""

    def test_plain_json(self):
        """Test plain JSON is returned unchanged."""
        output = '{"type": "feature", "level": "simple"}'
        result = _sanitize_json_output(output)
        assert result == output

    def test_strips_markdown_json_fence(self):
        """Test stripping ```json code fences."""
        output = '```json\n{"type": "feature", "level": "simple"}\n```'
        result = _sanitize_json_output(output)
        assert result == '{"type": "feature", "level": "simple"}'

    def test_strips_plain_markdown_fence(self):
        """Test stripping ``` code fences (no language)."""
        output = '```\n{"type": "feature"}\n```'
        result = _sanitize_json_output(output)
        assert result == '{"type": "feature"}'

    def test_strips_whitespace_around_fences(self):
        """Test stripping whitespace around code fences."""
        output = '  \n```json\n{"type": "feature"}\n```  \n'
        result = _sanitize_json_output(output)
        assert result == '{"type": "feature"}'

    def test_trims_leading_prose(self):
        """Test trimming leading prose before JSON object."""
        output = 'Here is the classification result:\n{"type": "bug", "level": "average"}'
        result = _sanitize_json_output(output)
        assert result == '{"type": "bug", "level": "average"}'

    def test_trims_trailing_prose(self):
        """Test trimming trailing prose after JSON object."""
        output = '{"type": "bug", "level": "average"}\nI hope this helps!'
        result = _sanitize_json_output(output)
        assert result == '{"type": "bug", "level": "average"}'

    def test_trims_surrounding_prose(self):
        """Test trimming both leading and trailing prose."""
        output = (
            "Based on my analysis, here is the result:\n"
            '{"status": "completed", "summary": "Done"}\n'
            "Let me know if you need anything else."
        )
        result = _sanitize_json_output(output)
        assert result == '{"status": "completed", "summary": "Done"}'

    def test_handles_empty_string(self):
        """Test handling empty string."""
        result = _sanitize_json_output("")
        assert result == ""

    def test_handles_whitespace_only(self):
        """Test handling whitespace-only string."""
        result = _sanitize_json_output("   \n\n  ")
        assert result == ""

    def test_no_json_object(self):
        """Test handling string with no JSON object."""
        output = "Just some plain text"
        result = _sanitize_json_output(output)
        assert result == output


class TestParseAndValidateJson:
    """Tests for parse_and_validate_json function."""

    def test_valid_json(self, mock_logger):
        """Test parsing valid JSON with all required fields."""
        output = '{"type": "feature", "level": "simple"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data == {"type": "feature", "level": "simple"}
        assert result.error is None

    def test_json_with_markdown_fences(self, mock_logger):
        """Test parsing JSON wrapped in markdown code fences."""
        output = '```json\n{"type": "bug", "level": "complex"}\n```'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data == {"type": "bug", "level": "complex"}

    def test_json_with_surrounding_prose(self, mock_logger):
        """Test parsing JSON with surrounding prose."""
        output = (
            "Here is the result:\n"
            '{"status": "completed", "summary": "Task done"}\n'
            "Hope this helps!"
        )
        required_fields = {"status": str, "summary": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data == {"status": "completed", "summary": "Task done"}

    def test_missing_required_field(self, mock_logger):
        """Test failure when required field is missing."""
        output = '{"type": "feature"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert result.data is None
        assert "Missing required field: 'level'" in result.error

    def test_wrong_field_type_string_instead_of_list(self, mock_logger):
        """Test failure when field has wrong type (string instead of list)."""
        output = '{"items": "not-a-list", "count": 5}'
        required_fields = {"items": list, "count": int}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Field 'items' has wrong type: expected list, got str" in result.error

    def test_wrong_field_type_int_instead_of_str(self, mock_logger):
        """Test failure when field has wrong type (int instead of str)."""
        output = '{"name": 123}'
        required_fields = {"name": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Field 'name' has wrong type: expected str, got int" in result.error

    def test_malformed_json(self, mock_logger):
        """Test failure with malformed JSON."""
        output = '{"type": "feature", level: simple}'  # Missing quotes around keys/values
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Invalid JSON" in result.error

    def test_empty_output(self, mock_logger):
        """Test failure with empty output."""
        output = ""
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Empty output received" in result.error

    def test_whitespace_only_output(self, mock_logger):
        """Test failure with whitespace-only output."""
        output = "   \n\n   "
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Empty output received" in result.error

    def test_json_array_instead_of_object(self, mock_logger):
        """Test failure when JSON is an array instead of object."""
        output = '["item1", "item2"]'
        required_fields = {"items": list}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert not result.success
        assert "Expected JSON object, got list" in result.error

    def test_with_step_name_in_error(self, mock_logger):
        """Test step name is included in error messages."""
        output = '{"wrong": "data"}'
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields, mock_logger, step_name="classify")

        assert not result.success
        assert "[classify]" in result.error

    def test_complex_required_fields(self, mock_logger):
        """Test validation with multiple field types."""
        output = (
            '{"status": "completed", "files_modified": ["a.py", "b.py"], '
            '"summary": "Done", "count": 42}'
        )
        required_fields = {
            "status": str,
            "files_modified": list,
            "summary": str,
            "count": int,
        }

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data["status"] == "completed"
        assert result.data["files_modified"] == ["a.py", "b.py"]
        assert result.data["count"] == 42

    def test_extra_fields_allowed(self, mock_logger):
        """Test that extra fields beyond required ones are allowed."""
        output = '{"type": "feature", "level": "simple", "extra": "ignored"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data["extra"] == "ignored"

    def test_empty_required_fields(self, mock_logger):
        """Test parsing with no required fields (just validates it's valid JSON)."""
        output = '{"anything": "goes"}'
        required_fields = {}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data == {"anything": "goes"}

    def test_nested_json_objects(self, mock_logger):
        """Test parsing JSON with nested objects."""
        output = '{"status": "ok", "data": {"nested": "value"}}'
        required_fields = {"status": str, "data": dict}

        result = parse_and_validate_json(output, required_fields, mock_logger)

        assert result.success
        assert result.data["data"] == {"nested": "value"}

    def test_none_output(self, mock_logger):
        """Test handling None output."""
        result = parse_and_validate_json(None, {"type": str}, mock_logger)

        assert not result.success
        assert "Empty output received" in result.error
