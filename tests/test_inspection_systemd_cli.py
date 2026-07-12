"""
Unit tests for MOD-INSP-003: inspection_cli.
@author sub_agent_test_engineer
@module MOD-INSP-003
@covers REQ-INSP-010, REQ-INSP-014, REQ-INSP-017
@test_level UNIT

Note: inspection_cli.py uses lazy imports (imports inside functions), so we patch
at the source module level rather than the importing module.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import patch, MagicMock

from src.inspection_cli import (
    InspectionCLI,
    CLIExitCode,
    CPU_THRESHOLD,
)


class TestCLIExitCode:
    """TC-UNIT-070: CLIExitCode enumeration."""

    def test_enum_values(self):
        """TC-UNIT-070: CLIExitCode values are 0/1/2."""
        assert CLIExitCode.SUCCESS.value == 0
        assert CLIExitCode.PARTIAL.value == 1
        assert CLIExitCode.FAILURE.value == 2

    def test_enum_is_int(self):
        """CLIExitCode is an IntEnum."""
        assert isinstance(CLIExitCode.SUCCESS, int)
        assert CLIExitCode.SUCCESS == 0


class TestLoadInspectionConfig:
    """TC-UNIT-071~073: load_inspection_config.

    Patching strategy: The functions in inspection_cli.py use lazy imports
    like `from src.database.repositories.inspection_repository import InspectionRepository`
    and `from src.security.config_manager import ConfigManager`.
    We patch at those source modules.
    """

    @pytest.fixture
    def cli(self):
        return InspectionCLI()

    def test_load_from_sqlite(self, cli):
        """TC-UNIT-071: load_inspection_config reads from SQLite."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        mock_repo = MagicMock()
        mock_repo.get_config.return_value = {
            "inspection.interval_minutes": "10",
            "diagnosis.timeout_seconds": "30",
            "diagnosis.retry_max": "3",
            "diagnosis.retry_backoff": "5",
        }

        mock_cm = MagicMock()
        mock_cm.get.return_value = None

        with patch(
            "src.database.repositories.inspection_repository.InspectionRepository",
            return_value=mock_repo
        ):
            with patch(
                "src.security.config_manager.ConfigManager",
                return_value=mock_cm
            ):
                result = cli.load_inspection_config()

        assert result["inspection.interval_minutes"] == "10"
        assert result["diagnosis.retry_backoff"] == "5"

    def test_sqlite_priority_over_config_yaml(self, cli):
        """TC-UNIT-072: SQLite values take priority over config.yaml."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        mock_repo = MagicMock()
        mock_repo.get_config.return_value = {
            "inspection.interval_minutes": "15",
        }

        mock_cm = MagicMock()
        mock_cm.get.return_value = "5"

        with patch(
            "src.database.repositories.inspection_repository.InspectionRepository",
            return_value=mock_repo
        ):
            with patch(
                "src.security.config_manager.ConfigManager",
                return_value=mock_cm
            ):
                result = cli.load_inspection_config()

        assert result["inspection.interval_minutes"] == "15"

    def test_fallback_to_config_yaml(self, cli):
        """TC-UNIT-073: fallback to config.yaml when SQLite has no value."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        mock_repo = MagicMock()
        mock_repo.get_config.return_value = {}

        mock_cm = MagicMock()
        mock_cm.get.return_value = "30"

        with patch(
            "src.database.repositories.inspection_repository.InspectionRepository",
            return_value=mock_repo
        ):
            with patch(
                "src.security.config_manager.ConfigManager",
                return_value=mock_cm
            ):
                result = cli.load_inspection_config()

        assert result["diagnosis.timeout_seconds"] == "30"

    def test_fallback_to_defaults(self, cli):
        """load_inspection_config uses hardcoded defaults when nothing available."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        mock_repo = MagicMock()
        mock_repo.get_config.return_value = {}

        mock_cm = MagicMock()
        mock_cm.get.return_value = None

        with patch(
            "src.database.repositories.inspection_repository.InspectionRepository",
            return_value=mock_repo
        ):
            with patch(
                "src.security.config_manager.ConfigManager",
                return_value=mock_cm
            ):
                result = cli.load_inspection_config()

        assert result["diagnosis.retry_backoff"] == "5"
        assert result["diagnosis.retry_max"] == "3"
        assert result["diagnosis.timeout_seconds"] == "30"

    def test_no_db_session_falls_back(self, cli):
        """load_inspection_config works without DB session (uses fallback)."""
        cli._db_session = None

        mock_cm = MagicMock()
        mock_cm.get.return_value = "7"

        with patch(
            "src.security.config_manager.ConfigManager",
            return_value=mock_cm
        ):
            result = cli.load_inspection_config()

        assert result is not None
        assert "diagnosis.retry_backoff" in result


class TestLoadDeviceList:
    """TC-UNIT-074~075: load_device_list."""

    @pytest.fixture
    def cli(self):
        return InspectionCLI()

    def test_load_devices_from_db(self, cli):
        """TC-UNIT-074: load_device_list returns devices from DB."""
        mock_session = MagicMock()
        mock_device1 = MagicMock()
        mock_device1.device_name = "Core-SW-01"
        mock_device1.device_ip = "192.168.1.1"
        mock_device1.device_model = "T2600G-28TS"
        mock_device2 = MagicMock()
        mock_device2.device_name = "Access-SW-02"
        mock_device2.device_ip = "192.168.1.2"
        mock_device2.device_model = "T2600G-28TS"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_device1, mock_device2]
        mock_session.execute.return_value = mock_result
        cli._db_session = mock_session

        # We need to mock sqlalchemy.select at the point of import in the function
        # The function does: from sqlalchemy import select
        with patch("sqlalchemy.select") as mock_select:
            mock_select.return_value = MagicMock()
            result = cli.load_device_list()

        assert len(result) == 2
        assert result[0]["device_name"] == "Core-SW-01"
        assert result[0]["device_ip"] == "192.168.1.1"

    def test_load_devices_empty_when_no_db(self, cli):
        """TC-UNIT-075: load_device_list returns [] when no DB session."""
        cli._db_session = None
        result = cli.load_device_list()
        assert result == []

    def test_load_devices_empty_db(self, cli):
        """load_device_list returns [] when DB has no devices."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        cli._db_session = mock_session

        # The method uses: from src.database.device_models import Device as DbDevice
        with patch("src.database.device_models.Device") as mock_dev:
            result = cli.load_device_list()
        assert result == []


class TestCLIRun:
    """TC-UNIT-076: CLI run flow."""

    @pytest.fixture
    def cli(self):
        return InspectionCLI()

    def test_run_empty_devices_returns_success(self, cli):
        """TC-UNIT-076: CLI run with no devices returns SUCCESS."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        with patch.object(cli, "_init_db"):
            with patch.object(cli, "load_inspection_config") as mock_cfg:
                mock_cfg.return_value = {
                    "inspection.interval_minutes": "10",
                    "diagnosis.timeout_seconds": "30",
                    "diagnosis.retry_max": "3",
                    "diagnosis.retry_backoff": "5",
                }
                with patch.object(cli, "load_device_list") as mock_devs:
                    mock_devs.return_value = []
                    with patch.object(cli, "_close_db"):
                        result = cli.run()
        assert result == CLIExitCode.SUCCESS

    def test_run_db_init_failure_returns_failure(self, cli):
        """CLI run returns FAILURE when DB init fails."""
        with patch.object(cli, "_init_db") as mock_init:
            mock_init.side_effect = RuntimeError("DB init failed")
            result = cli.run()
        assert result == CLIExitCode.FAILURE

    def test_run_config_load_failure_returns_failure(self, cli):
        """CLI run returns FAILURE when config load fails."""
        mock_session = MagicMock()
        cli._db_session = mock_session

        with patch.object(cli, "_init_db"):
            with patch.object(cli, "load_inspection_config") as mock_cfg:
                mock_cfg.side_effect = Exception("config broke")
                with patch.object(cli, "_close_db"):
                    result = cli.run()
        assert result == CLIExitCode.FAILURE

    def test_cpu_threshold_constant(self):
        """CPU_THRESHOLD constant is 80."""
        assert CPU_THRESHOLD == 80


class TestMainEntry:
    """Test main() CLI entry point."""

    def test_main_with_run_command(self):
        """main('run') calls _run_command."""
        with patch.object(sys, "argv", ["inspection_cli", "run"]):
            with patch("src.inspection_cli.InspectionCLI") as mock_cli_cls:
                mock_cli = MagicMock()
                mock_cli.run.return_value = CLIExitCode.SUCCESS
                mock_cli_cls.return_value = mock_cli
                with patch("sys.exit") as mock_exit:
                    # Need to import main fresh since it was already loaded
                    from src.inspection_cli import main
                    main()
                mock_exit.assert_called_once_with(0)

    def test_main_no_command_shows_help(self):
        """main with no args prints help and exits with FAILURE.

        We mock argparse.ArgumentParser.parse_args directly to avoid
        interference from pytest's own sys.argv.
        """
        from unittest.mock import patch as _patch
        from src.inspection_cli import main as cli_main

        # Mock parse_args to return namespace with command=None
        mock_ns = MagicMock()
        mock_ns.command = None
        with _patch("argparse.ArgumentParser.parse_args", return_value=mock_ns):
            with _patch("sys.exit") as mock_exit:
                cli_main()
            mock_exit.assert_called_once_with(CLIExitCode.FAILURE)
