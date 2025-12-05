"""Unit tests for paths module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cape.core.paths import CapePaths


class TestCapePaths:
    """Test CapePaths class."""

    @pytest.mark.xfail(
        sys.platform.startswith("win"),
        reason="Path.home() unavailable in some Windows CI environments",
        strict=False,
    )
    def test_get_base_dir_default(self):
        """Test default base directory."""
        with patch.dict(os.environ, {}, clear=True):
            base_dir = CapePaths.get_base_dir()
            assert base_dir == Path.home() / ".cape"

    def test_get_base_dir_with_env_var(self):
        """Test base directory with CAPE_DATA_DIR environment variable."""
        with patch.dict(os.environ, {"CAPE_DATA_DIR": "/tmp/custom_cape"}):
            base_dir = CapePaths.get_base_dir()
            assert base_dir == Path("/tmp/custom_cape")

    @pytest.mark.xfail(
        sys.platform.startswith("win"),
        reason="Path.home() unavailable in some Windows CI environments",
        strict=False,
    )
    def test_get_logs_dir(self):
        """Test logs directory."""
        with patch.dict(os.environ, {}, clear=True):
            logs_dir = CapePaths.get_logs_dir()
            assert logs_dir == Path.home() / ".cape" / "logs"

    def test_get_logs_dir_with_env_var(self):
        """Test logs directory with CAPE_DATA_DIR environment variable."""
        with patch.dict(os.environ, {"CAPE_DATA_DIR": "/tmp/custom_cape"}):
            logs_dir = CapePaths.get_logs_dir()
            assert logs_dir == Path("/tmp/custom_cape") / "logs"

    def test_ensure_directories(self, tmp_path):
        """Test directory creation with ensure_directories."""
        with patch.dict(os.environ, {"CAPE_DATA_DIR": str(tmp_path)}):
            CapePaths.ensure_directories()

            # Check that logs directory was created
            assert (tmp_path / "logs").exists()

            # Check that directory is accessible
            assert (tmp_path / "logs").is_dir()

    def test_ensure_directories_idempotent(self, tmp_path):
        """Test that ensure_directories can be called multiple times safely."""
        with patch.dict(os.environ, {"CAPE_DATA_DIR": str(tmp_path)}):
            # Call twice - should not raise exception
            CapePaths.ensure_directories()
            CapePaths.ensure_directories()

            # Directory should still exist
            assert (tmp_path / "logs").exists()
