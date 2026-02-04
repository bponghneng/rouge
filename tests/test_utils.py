"""Tests for utility functions."""

import logging
from pathlib import Path
from unittest.mock import patch

from rouge.core.utils import get_logger, make_adw_id, setup_logger


def test_make_adw_id() -> None:
    """Test ADW ID generation."""
    adw_id = make_adw_id()
    assert len(adw_id) == 8
    assert isinstance(adw_id, str)


def test_make_adw_id_unique() -> None:
    """Test that ADW IDs are unique."""
    id1 = make_adw_id()
    id2 = make_adw_id()
    assert id1 != id2


def test_setup_logger(tmp_path: Path) -> None:
    """Test logger setup with temp directory."""
    # Mock get_working_dir to return tmp_path so logs go under tmp_path/.rouge/agents/logs/
    with patch("rouge.core.workflow.shared.get_working_dir", return_value=str(tmp_path)):
        adw_id = "test1234"
        logger = setup_logger(adw_id, "test_trigger")

        assert logger.name == f"rouge_{adw_id}"
        assert logger.level == logging.DEBUG

        # Check log directory was created
        expected_dir = tmp_path / ".rouge" / "agents" / "logs" / adw_id / "test_trigger"
        assert expected_dir.exists()

        # Check log file was created
        log_file = expected_dir / "execution.log"
        assert log_file.exists()

        # Check handlers
        assert len(logger.handlers) == 2

        # Clean up - close handlers before clearing
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()


def test_setup_logger_file_handler(tmp_path: Path) -> None:
    """Test logger file handler writes correctly."""
    with patch("rouge.core.workflow.shared.get_working_dir", return_value=str(tmp_path)):
        adw_id = "test5678"
        logger = setup_logger(adw_id)
        logger.debug("Debug message")
        logger.info("Info message")

        log_file = (
            tmp_path / ".rouge" / "agents" / "logs" / adw_id / "adw_plan_build" / "execution.log"
        )
        content = log_file.read_text()

        assert "Debug message" in content
        assert "Info message" in content

        # Clean up - close handlers before clearing
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()


def test_get_logger() -> None:
    """Test getting existing logger."""
    adw_id = "test9999"
    logger = logging.getLogger(f"rouge_{adw_id}")
    retrieved = get_logger(adw_id)
    assert retrieved is logger
