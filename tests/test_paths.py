"""Unit tests for paths module."""

from pathlib import Path
from unittest.mock import patch

from rouge.core.paths import RougePaths

_WORKING_DIR_PATCH = "rouge.core.paths.get_working_dir"


class TestRougePaths:
    """Test RougePaths class."""

    def test_get_base_dir_default(self):
        """Test default base directory uses get_working_dir()."""
        with patch(_WORKING_DIR_PATCH, return_value="/home/user/project"):
            base_dir = RougePaths.get_base_dir()
            assert base_dir == Path("/home/user/project/.rouge")

    def test_get_base_dir_with_working_dir(self):
        """Test base directory with custom working directory."""
        with patch(_WORKING_DIR_PATCH, return_value="/tmp/custom_rouge"):
            base_dir = RougePaths.get_base_dir()
            assert base_dir == Path("/tmp/custom_rouge/.rouge")

    def test_get_logs_dir(self):
        """Test logs directory."""
        with patch(_WORKING_DIR_PATCH, return_value="/home/user/project"):
            logs_dir = RougePaths.get_logs_dir()
            assert logs_dir == Path("/home/user/project/.rouge/logs")

    def test_get_logs_dir_with_working_dir(self):
        """Test logs directory with custom working directory."""
        with patch(_WORKING_DIR_PATCH, return_value="/tmp/custom_rouge"):
            logs_dir = RougePaths.get_logs_dir()
            assert logs_dir == Path("/tmp/custom_rouge/.rouge/logs")

    def test_ensure_directories(self, tmp_path):
        """Test directory creation with ensure_directories."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            RougePaths.ensure_directories()

            # Check that logs directory was created
            assert (tmp_path / ".rouge" / "logs").exists()

            # Check that directory is accessible
            assert (tmp_path / ".rouge" / "logs").is_dir()

    def test_ensure_directories_idempotent(self, tmp_path):
        """Test that ensure_directories can be called multiple times safely."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Call twice - should not raise exception
            RougePaths.ensure_directories()
            RougePaths.ensure_directories()

            # Directory should still exist
            assert (tmp_path / ".rouge" / "logs").exists()
