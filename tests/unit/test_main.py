from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from laffyhand.main import entry_point, main, parse_args


class TestParseArgs:
    def test_gateway_serve_defaults(self):
        with patch("laffyhand.main.sys.argv", ["laffyhand", "gateway", "serve"]):
            args = parse_args()
        assert args.command == "gateway"
        assert args.gateway_command == "serve"
        assert args.listen == "stdio://"
        assert args.host == "127.0.0.1"
        assert args.port == 9090

    def test_gateway_serve_with_flags(self):
        with patch(
            "laffyhand.main.sys.argv",
            [
                "laffyhand",
                "gateway",
                "serve",
                "--listen",
                "ws://0.0.0.0:8080",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
            ],
        ):
            args = parse_args()
        assert args.command == "gateway"
        assert args.gateway_command == "serve"
        assert args.listen == "ws://0.0.0.0:8080"
        assert args.host == "0.0.0.0"
        assert args.port == 8080

    def test_ui_defaults(self):
        with patch("laffyhand.main.sys.argv", ["laffyhand", "ui"]):
            args = parse_args()
        assert args.command == "ui"
        assert args.host == "127.0.0.1"
        assert args.port == 9090

    def test_ui_with_flags(self):
        with patch(
            "laffyhand.main.sys.argv",
            ["laffyhand", "ui", "--host", "0.0.0.0", "--port", "3000"],
        ):
            args = parse_args()
        assert args.command == "ui"
        assert args.host == "0.0.0.0"
        assert args.port == 3000

    def test_config_flag(self):
        with patch(
            "laffyhand.main.sys.argv",
            ["laffyhand", "--config", "/custom/path.yml", "gateway", "serve"],
        ):
            args = parse_args()
        assert args.config == "/custom/path.yml"
        assert args.command == "gateway"
        assert args.gateway_command == "serve"


class TestEntryPoint:
    @patch("laffyhand.main.asyncio.run")
    def test_wraps_main_in_asyncio_run(self, mock_asyncio_run):
        with patch("laffyhand.main.main", new_callable=AsyncMock):
            entry_point()
        mock_asyncio_run.assert_called_once()
        call_arg = mock_asyncio_run.call_args[0][0]
        assert hasattr(call_arg, "__await__")

    @patch("laffyhand.main.asyncio.run")
    def test_handles_exception_gracefully(self, mock_asyncio_run):
        mock_asyncio_run.side_effect = Exception("test error")
        with patch("laffyhand.main.logger") as mock_logger:
            with pytest.raises(SystemExit) as exc_info:
                entry_point()
        assert exc_info.value.code == 1
        mock_logger.exception.assert_called_once_with("Unhandled exception")


class TestConfigPropagation:
    @patch("laffyhand.main._run_gateway_serve", new_callable=AsyncMock)
    @patch("laffyhand.main.setup_logging")
    @patch("laffyhand.main.load_config")
    @patch("laffyhand.main.parse_args")
    @pytest.mark.anyio
    async def test_config_loaded_and_propagated_to_setup_logging(
        self,
        mock_parse_args,
        mock_load_config,
        mock_setup_logging,
        mock_run_gateway,
    ):
        mock_config = MagicMock()
        mock_config.logging.dir = "/tmp/logs"
        mock_config.logging.level = "DEBUG"
        mock_config.logging.retention_days = 7
        mock_config.logging.console = True
        mock_load_config.return_value = mock_config

        mock_parse_args.return_value = argparse.Namespace(
            command="gateway",
            gateway_command="serve",
            config="/custom/config.yml",
            listen="stdio://",
            host="127.0.0.1",
            port=9090,
        )

        await main()

        mock_load_config.assert_called_once_with("/custom/config.yml")
        mock_setup_logging.assert_called_once_with(
            log_dir="/tmp/logs",
            level="DEBUG",
            retention=7,
            console=True,
        )
        mock_run_gateway.assert_called_once()

    @patch("laffyhand.main._run_gateway_serve", new_callable=AsyncMock)
    @patch("laffyhand.main.setup_logging")
    @patch("laffyhand.main.load_config")
    @patch("laffyhand.main.parse_args")
    @pytest.mark.anyio
    async def test_config_path_none_when_not_specified(
        self,
        mock_parse_args,
        mock_load_config,
        mock_setup_logging,
        mock_run_gateway,
    ):
        mock_config = MagicMock()
        mock_config.logging.dir = "logs"
        mock_config.logging.level = "INFO"
        mock_config.logging.retention_days = 10
        mock_config.logging.console = False
        mock_load_config.return_value = mock_config

        mock_parse_args.return_value = argparse.Namespace(
            command="gateway",
            gateway_command="serve",
            config=None,
            listen="stdio://",
            host="127.0.0.1",
            port=9090,
        )

        await main()

        mock_load_config.assert_called_once_with(None)
        mock_setup_logging.assert_called_once_with(
            log_dir="logs",
            level="INFO",
            retention=10,
            console=False,
        )

    @patch("laffyhand.main.setup_logging")
    @patch("laffyhand.main.load_config")
    @patch("laffyhand.main.parse_args")
    @pytest.mark.anyio
    async def test_ui_path_loads_config(
        self,
        mock_parse_args,
        mock_load_config,
        mock_setup_logging,
    ):
        mock_config = MagicMock()
        mock_config.logging.dir = "logs"
        mock_config.logging.level = "INFO"
        mock_config.logging.retention_days = 10
        mock_config.logging.console = False
        mock_load_config.return_value = mock_config

        mock_parse_args.return_value = argparse.Namespace(
            command="ui",
            config=None,
            host="127.0.0.1",
            port=9090,
        )

        with (
            patch(
                "laffyhand.main.create_runtime", new_callable=AsyncMock
            ) as mock_create,
            patch(
                "laffyhand.ui_server.run_ui_server", new_callable=AsyncMock
            ) as mock_ui,
        ):
            mock_runtime = AsyncMock()
            mock_create.return_value = mock_runtime
            await main()

        mock_load_config.assert_called_once_with(None)
        mock_create.assert_called_once_with(mock_config)
        mock_ui.assert_called_once_with(mock_runtime, host="127.0.0.1", port=9090)
        mock_runtime.shutdown.assert_awaited_once()
