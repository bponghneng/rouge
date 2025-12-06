"""Unit tests for paths module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rouge.core.paths import RougePaths


class TestRougePaths:
    """Test RougePaths class."""

    @pytest.mark.xfail(
        sys.platform.startswith("win"),
        reason="Path.home() unavailable in some Windows CI environments",
        strict=False,
    )
    def test_get_base_dir_default(self):
        """Test default base directory."""
        with patch.dict(os.environ, {}, clear=True):
            base_dir = RougePaths.get_base_dir()
            assert base_dir == Path.home() / ".rouge"

    def test_get_base_dir_with_env_var(self):
        """Test base directory with ROUGE_DATA_DIR environment variable."""
        with patch.dict(os.environ, {"ROUGE_DATA_DIR": "/tmp/custom_rouge"}):
            base_dir = RougePaths.get_base_dir()
            assert base_dir == Path("/tmp/custom_rouge")

    @pytest.mark.xfail(
        sys.platform.startswith("win"),
        reason="Path.home() unavailable in some Windows CI environments",
        strict=False,
    )
    def test_get_logs_dir(self):
        """Test logs directory."""
        with patch.dict(os.environ, {}, clear=True):
            logs_dir = RougePaths.get_logs_dir()
            assert logs_dir == Path.home() / ".rouge" / "logs"

    def test_get_logs_dir_with_env_var(self):
        """Test logs directory with ROUGE_DATA_DIR environment variable."""
        with patch.dict(os.environ, {"ROUGE_DATA_DIR": "/tmp/custom_rouge"}):
            logs_dir = RougePaths.get_logs_dir()
            assert logs_dir == Path("/tmp/custom_rouge") / "logs"

    def test_ensure_directories(self, tmp_path):
        """Test directory creation with ensure_directories."""
        with patch.dict(os.environ, {"ROUGE_DATA_DIR": str(tmp_path)}):
            RougePaths.ensure_directories()

            # Check that logs directory was created
            assert (tmp_path / "logs").exists()

            # Check that directory is accessible
            assert (tmp_path / "logs").is_dir()

    def test_ensure_directories_idempotent(self, tmp_path):
        """Test that ensure_directories can be called multiple times safely."""
        with patch.dict(os.environ, {"ROUGE_DATA_DIR": str(tmp_path)}):
            # Call twice - should not raise exception
            RougePaths.ensure_directories()
            RougePaths.ensure_directories()

            # Directory should still exist
            assert (tmp_path / "logs").exists()
