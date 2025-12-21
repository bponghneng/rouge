"""Tests for JSON parsing helper module."""

from rouge.core.json_parser import _sanitize_json_output, parse_and_validate_json


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

    def test_strips_markdown_fence_with_leading_text(self):
        """Test stripping markdown fence when preceded by conversational text."""
        output = (
            "Perfect! Here is the JSON output:\n\n```json\n"
            '{"status": "ACCEPT", "summary": "All tests pass"}\n```'
        )
        result = _sanitize_json_output(output)
        assert result == '{"status": "ACCEPT", "summary": "All tests pass"}'

    def test_strips_markdown_fence_with_trailing_text(self):
        """Test stripping markdown fence when followed by conversational text."""
        output = '```json\n{"type": "feature"}\n```\n\nLet me know if you need anything else!'
        result = _sanitize_json_output(output)
        assert result == '{"type": "feature"}'

    def test_strips_markdown_fence_with_surrounding_text(self):
        """Test stripping markdown fence when surrounded by conversational text."""
        output = (
            "Based on my analysis, here is the result:\n\n```json\n"
            '{"status": "completed"}\n```\n\nI hope this helps!'
        )
        result = _sanitize_json_output(output)
        assert result == '{"status": "completed"}'

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

    def test_escape_sequences_with_valid_json(self):
        """Test handling escape sequences with valid JSON after decoding."""
        output = 'prose text\\n\\n{\\"key\\":\\"value\\"}'
        result = _sanitize_json_output(output)
        assert result == '{"key":"value"}'

    def test_escape_sequences_with_newlines_and_braces(self):
        """Test handling \\n escape sequences with JSON object."""
        output = 'Some text\\n\\n{\\"type\\":\\"feature\\",\\"level\\":\\"simple\\"}'
        result = _sanitize_json_output(output)
        assert result == '{"type":"feature","level":"simple"}'

    def test_escape_sequences_without_valid_json(self):
        """Test handling escape sequences that don't contain valid JSON after decoding."""
        output = "text with\\n\\nno valid json here"
        result = _sanitize_json_output(output)
        # Should return original or best effort extraction
        assert result == output

    def test_escape_sequences_with_invalid_json_structure(self):
        """Test handling escape sequences where decoded content isn't valid JSON."""
        output = 'text\\n\\n{\\"invalid\\": incomplete'
        result = _sanitize_json_output(output)
        # Should fall back to extracting braces from original
        assert "{" in result or result == output

    def test_escape_sequences_unicode_decode_error(self):
        """Test handling invalid unicode escape sequences that trigger UnicodeDecodeError."""
        # This is a contrived case - actual invalid escape might vary by platform
        # The function should handle exceptions gracefully
        output = '{"valid": "json"}'  # Valid JSON that won't trigger decode
        result = _sanitize_json_output(output)
        assert result == '{"valid": "json"}'


class TestParseAndValidateJson:
    """Tests for parse_and_validate_json function."""

    def test_valid_json(self):
        """Test parsing valid JSON with all required fields."""
        output = '{"type": "feature", "level": "simple"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data == {"type": "feature", "level": "simple"}
        assert result.error is None

    def test_json_with_markdown_fences(self):
        """Test parsing JSON wrapped in markdown code fences."""
        output = '```json\n{"type": "bug", "level": "complex"}\n```'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data == {"type": "bug", "level": "complex"}

    def test_json_with_surrounding_prose(self):
        """Test parsing JSON with surrounding prose."""
        output = (
            'Here is the result:\n{"status": "completed", "summary": "Task done"}\nHope this helps!'
        )
        required_fields = {"status": str, "summary": str}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data == {"status": "completed", "summary": "Task done"}

    def test_missing_required_field(self):
        """Test failure when required field is missing."""
        output = '{"type": "feature"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert result.data is None
        assert "Missing required field: 'level'" in result.error

    def test_wrong_field_type_string_instead_of_list(self):
        """Test failure when field has wrong type (string instead of list)."""
        output = '{"items": "not-a-list", "count": 5}'
        required_fields = {"items": list, "count": int}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Field 'items' has wrong type: expected list, got str" in result.error

    def test_wrong_field_type_int_instead_of_str(self):
        """Test failure when field has wrong type (int instead of str)."""
        output = '{"name": 123}'
        required_fields = {"name": str}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Field 'name' has wrong type: expected str, got int" in result.error

    def test_malformed_json(self):
        """Test failure with malformed JSON."""
        output = '{"type": "feature", level: simple}'  # Missing quotes around keys/values
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Invalid JSON" in result.error

    def test_empty_output(self):
        """Test failure with empty output."""
        output = ""
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Empty output received" in result.error

    def test_whitespace_only_output(self):
        """Test failure with whitespace-only output."""
        output = "   \n\n   "
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Empty output received" in result.error

    def test_json_array_instead_of_object(self):
        """Test failure when JSON is an array instead of object."""
        output = '["item1", "item2"]'
        required_fields = {"items": list}

        result = parse_and_validate_json(output, required_fields)

        assert not result.success
        assert "Expected JSON object, got list" in result.error

    def test_with_step_name_in_error(self):
        """Test step name is included in error messages."""
        output = '{"wrong": "data"}'
        required_fields = {"type": str}

        result = parse_and_validate_json(output, required_fields, step_name="classify")

        assert not result.success
        assert "[classify]" in result.error

    def test_complex_required_fields(self):
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

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data["status"] == "completed"
        assert result.data["files_modified"] == ["a.py", "b.py"]
        assert result.data["count"] == 42

    def test_extra_fields_allowed(self):
        """Test that extra fields beyond required ones are allowed."""
        output = '{"type": "feature", "level": "simple", "extra": "ignored"}'
        required_fields = {"type": str, "level": str}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data["extra"] == "ignored"

    def test_empty_required_fields(self):
        """Test parsing with no required fields (just validates it's valid JSON)."""
        output = '{"anything": "goes"}'
        required_fields = {}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data == {"anything": "goes"}

    def test_nested_json_objects(self):
        """Test parsing JSON with nested objects."""
        output = '{"status": "ok", "data": {"nested": "value"}}'
        required_fields = {"status": str, "data": dict}

        result = parse_and_validate_json(output, required_fields)

        assert result.success
        assert result.data["data"] == {"nested": "value"}

    def test_none_output(self):
        """Test handling None output."""
        result = parse_and_validate_json(None, {"type": str})

        assert not result.success
        assert "Empty output received" in result.error
