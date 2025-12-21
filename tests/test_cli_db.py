"""Tests for db CLI commands."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.cli.db import get_database_url

runner = CliRunner()


class TestGetDatabaseUrl:
    """Tests for get_database_url helper function."""

    def test_returns_database_url_when_set(self):
        """Test that DATABASE_URL is returned when set."""
        with patch.dict(
            "os.environ", {"DATABASE_URL": "postgresql://test:pass@host/db"}, clear=True
        ):
            url = get_database_url()
            assert url == "postgresql://test:pass@host/db"

    def test_returns_supabase_url_when_database_url_not_set(self):
        """Test that SUPABASE_URL is used when DATABASE_URL is not set."""
        with patch.dict(
            "os.environ",
            {"SUPABASE_URL": "postgresql://supabase:pass@host/db"},
            clear=True,
        ):
            url = get_database_url()
            assert url == "postgresql://supabase:pass@host/db"

    def test_database_url_takes_precedence_over_supabase_url(self):
        """Test that DATABASE_URL takes precedence over SUPABASE_URL."""
        with patch.dict(
            "os.environ",
            {
                "DATABASE_URL": "postgresql://primary:pass@host/db",
                "SUPABASE_URL": "postgresql://supabase:pass@host/db",
            },
            clear=True,
        ):
            url = get_database_url()
            assert url == "postgresql://primary:pass@host/db"

    def test_raises_exit_when_no_url_set(self):
        """Test that typer.Exit is raised when no DATABASE_URL is set."""
        import typer

        with patch("rouge.cli.db.load_dotenv"):  # Prevent loading from .env file
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(typer.Exit) as exc_info:
                    get_database_url()
                assert exc_info.value.exit_code == 1


class TestDbMigrateCommand:
    """Tests for 'rouge db migrate' command."""

    def test_migrate_help_displays(self):
        """Test migrate command help is accessible."""
        result = runner.invoke(app, ["db", "migrate", "--help"])
        assert result.exit_code == 0
        assert "Apply all pending database migrations" in result.output

    def test_migrate_fails_without_database_url(self):
        """Test migrate fails gracefully when DATABASE_URL is missing."""
        with patch("rouge.cli.db.load_dotenv"):  # Prevent loading from .env file
            with patch.dict("os.environ", {}, clear=True):
                result = runner.invoke(app, ["db", "migrate"])
                assert result.exit_code != 0
                assert "DATABASE_URL" in result.output or "SUPABASE_URL" in result.output

    def test_migrate_calls_yoyo_apply(self):
        """Test migrate calls yoyo apply with correct arguments."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                runner.invoke(app, ["db", "migrate"])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "yoyo" in call_args
                assert "apply" in call_args
                assert "--batch" in call_args
                assert "--database" in call_args
                assert "postgresql://test@host/db" in call_args


class TestDbRollbackCommand:
    """Tests for 'rouge db rollback' command."""

    def test_rollback_help_displays(self):
        """Test rollback command help is accessible."""
        result = runner.invoke(app, ["db", "rollback", "--help"])
        assert result.exit_code == 0
        assert "Rollback database migrations" in result.output
        assert "--count" in result.output

    def test_rollback_fails_without_database_url(self):
        """Test rollback fails gracefully when DATABASE_URL is missing."""
        with patch("rouge.cli.db.load_dotenv"):  # Prevent loading from .env file
            with patch.dict("os.environ", {}, clear=True):
                result = runner.invoke(app, ["db", "rollback"])
                assert result.exit_code != 0
                assert "DATABASE_URL" in result.output or "SUPABASE_URL" in result.output

    def test_rollback_calls_yoyo_rollback(self):
        """Test rollback calls yoyo rollback with correct arguments."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                runner.invoke(app, ["db", "rollback"])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "yoyo" in call_args
                assert "rollback" in call_args
                assert "--batch" in call_args
                assert "--database" in call_args

    def test_rollback_with_count_option(self):
        """Test rollback with --count option includes revision flag."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                runner.invoke(app, ["db", "rollback", "--count", "2"])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "--revision" in call_args
                assert "2" in call_args

    def test_rollback_with_invalid_count(self):
        """Test rollback with invalid count value fails."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            result = runner.invoke(app, ["db", "rollback", "--count", "0"])
            assert result.exit_code != 0
            assert "at least 1" in result.output


class TestDbStatusCommand:
    """Tests for 'rouge db status' command."""

    def test_status_help_displays(self):
        """Test status command help is accessible."""
        result = runner.invoke(app, ["db", "status", "--help"])
        assert result.exit_code == 0
        assert "Show database migration status" in result.output

    def test_status_fails_without_database_url(self):
        """Test status fails gracefully when DATABASE_URL is missing."""
        with patch("rouge.cli.db.load_dotenv"):  # Prevent loading from .env file
            with patch.dict("os.environ", {}, clear=True):
                result = runner.invoke(app, ["db", "status"])
                assert result.exit_code != 0
                assert "DATABASE_URL" in result.output or "SUPABASE_URL" in result.output

    def test_status_calls_yoyo_list(self):
        """Test status calls yoyo list with correct arguments."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                runner.invoke(app, ["db", "status"])

                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "yoyo" in call_args
                assert "list" in call_args
                assert "--database" in call_args


class TestDbNewCommand:
    """Tests for 'rouge db new' command."""

    def test_new_help_displays(self):
        """Test new command help is accessible."""
        result = runner.invoke(app, ["db", "new", "--help"])
        assert result.exit_code == 0
        assert "Create a new migration file" in result.output

    def test_new_requires_name_argument(self):
        """Test new command requires name argument."""
        result = runner.invoke(app, ["db", "new"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_new_calls_yoyo_new(self):
        """Test new calls yoyo new with correct arguments."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            runner.invoke(app, ["db", "new", "add_users_table"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "yoyo" in call_args
            assert "new" in call_args
            assert "--batch" in call_args
            assert "--message" in call_args
            assert "add_users_table" in call_args

    def test_new_does_not_require_database_url(self):
        """Test new command works without DATABASE_URL (creates local file)."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                runner.invoke(app, ["db", "new", "test_migration"])

                # Should succeed - new doesn't need DATABASE_URL
                mock_run.assert_called_once()


class TestDbHelp:
    """Tests for 'rouge db' command group."""

    def test_db_help_shows_all_commands(self):
        """Test db help shows all available subcommands."""
        result = runner.invoke(app, ["db", "--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output
        assert "rollback" in result.output
        assert "status" in result.output
        assert "new" in result.output

    def test_db_appears_in_main_help(self):
        """Test db subcommand appears in main CLI help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "db" in result.output


class TestSubprocessErrorHandling:
    """Tests for subprocess error handling."""

    def test_migrate_propagates_subprocess_failure(self):
        """Test that subprocess failures are propagated correctly."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1

                result = runner.invoke(app, ["db", "migrate"])

                assert result.exit_code == 1

    def test_handles_missing_uv_command(self):
        """Test graceful handling when uv is not available."""
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://test@host/db"}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError()

                result = runner.invoke(app, ["db", "migrate"])

                assert result.exit_code == 1
                assert "uv" in result.output
