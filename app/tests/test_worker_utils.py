"""Tests for TUI worker utilities."""

from cape.tui.worker_utils import WORKER_OPTIONS, get_worker_display_name


class TestWorkerOptions:
    """Tests for WORKER_OPTIONS constant."""

    def test_worker_options_structure(self):
        """Test WORKER_OPTIONS has correct structure."""
        assert isinstance(WORKER_OPTIONS, list)
        assert len(WORKER_OPTIONS) > 0

        # Check each entry is a tuple with (display_name, worker_id)
        for entry in WORKER_OPTIONS:
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            display_name, worker_id = entry
            assert isinstance(display_name, str)
            assert worker_id is None or isinstance(worker_id, str)

    def test_worker_options_includes_all_workers(self):
        """Test WORKER_OPTIONS includes all expected workers."""
        worker_ids = [worker_id for _, worker_id in WORKER_OPTIONS]

        # Check for Unassigned
        assert None in worker_ids

        # Check for Alleycat workers
        assert "alleycat-1" in worker_ids
        assert "alleycat-2" in worker_ids
        assert "alleycat-3" in worker_ids

        # Check for HailMary workers
        assert "hailmary-1" in worker_ids
        assert "hailmary-2" in worker_ids
        assert "hailmary-3" in worker_ids

        # Check for Nebuchadnezzar workers
        assert "nebuchadnezzar-1" in worker_ids
        assert "nebuchadnezzar-2" in worker_ids
        assert "nebuchadnezzar-3" in worker_ids

        # Check for Tydirium workers
        assert "tydirium-1" in worker_ids
        assert "tydirium-2" in worker_ids
        assert "tydirium-3" in worker_ids


class TestGetWorkerDisplayName:
    """Tests for get_worker_display_name function."""

    def test_alleycat_workers(self):
        """Test correct mapping for Alleycat workers."""
        assert get_worker_display_name("alleycat-1") == "Alleycat 1"
        assert get_worker_display_name("alleycat-2") == "Alleycat 2"
        assert get_worker_display_name("alleycat-3") == "Alleycat 3"

    def test_hailmary_workers(self):
        """Test correct mapping for HailMary workers."""
        assert get_worker_display_name("hailmary-1") == "HailMary 1"
        assert get_worker_display_name("hailmary-2") == "HailMary 2"
        assert get_worker_display_name("hailmary-3") == "HailMary 3"

    def test_nebuchadnezzar_workers(self):
        """Test correct mapping for nebuchadnezzar workers."""
        assert get_worker_display_name("nebuchadnezzar-1") == "Nebuchadnezzar 1"
        assert get_worker_display_name("nebuchadnezzar-2") == "Nebuchadnezzar 2"
        assert get_worker_display_name("nebuchadnezzar-3") == "Nebuchadnezzar 3"

    def test_tydirium_workers(self):
        """Test correct mapping for Tydirium workers."""
        assert get_worker_display_name("tydirium-1") == "Tydirium 1"
        assert get_worker_display_name("tydirium-2") == "Tydirium 2"
        assert get_worker_display_name("tydirium-3") == "Tydirium 3"

    def test_none_input(self):
        """Test behavior for None input (unassigned)."""
        assert get_worker_display_name(None) == ""

    def test_unknown_worker_id(self):
        """Test behavior for unknown/invalid worker IDs."""
        assert get_worker_display_name("unknown-worker") == ""
        assert get_worker_display_name("invalid-1") == ""
        assert get_worker_display_name("") == ""

    def test_case_sensitivity(self):
        """Test that worker IDs are case-sensitive."""
        # Should not match uppercase variants
        assert get_worker_display_name("ALLEYCAT-1") == ""
        assert get_worker_display_name("Alleycat-1") == ""
