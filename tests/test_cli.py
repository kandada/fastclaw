# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""CLI 测试"""

import io
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from gateway.router import load_sessions as _load, save_sessions as _save
from fastclaw.core.config import get_sessions_dir
import shutil


def _cleanup_session(session_id: str):
    sessions = _load()
    if session_id in sessions:
        del sessions[session_id]
        _save(sessions)
    session_dir = get_sessions_dir() / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)


class TestHelp:
    """show_help 测试"""

    def test_help_output_contains_commands(self):
        from main import show_help

        with patch("sys.stdout", new_callable=io.StringIO) as buf:
            show_help()
        output = buf.getvalue()

        assert "FastClaw CLI" in output
        assert "start" in output
        assert "chat" in output
        assert "session list" in output
        assert "cron list" in output
        assert "skill list" in output
        assert "agent list" in output
        assert "api" in output
        assert "help" in output

    def test_help_does_not_advertise_unimplemented(self):
        from main import show_help

        with patch("sys.stdout", new_callable=io.StringIO) as buf:
            show_help()
        output = buf.getvalue()

        assert "session history" not in output
        assert "session clear" not in output
        assert "session export" not in output
        assert "cron add" not in output
        assert "cron del" not in output
        assert "cron run" not in output
        assert "skill info" not in output
        assert "skill test" not in output
        assert "agent info" not in output


class TestStatus:
    """status 命令测试"""

    def test_status_online(self):
        from main import status

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_resp

        with patch("main.get_http_opener", return_value=mock_opener), \
             patch("sys.stdout", new_callable=io.StringIO) as buf:
            status()
        output = buf.getvalue()

        assert "Status: ok" in output
        assert "Server: http://localhost:8765" in output

    def test_status_offline(self):
        from main import status

        mock_opener = MagicMock()
        mock_opener.open.side_effect = ConnectionRefusedError

        with patch("main.get_http_opener", return_value=mock_opener), \
             patch("sys.stdout", new_callable=io.StringIO) as buf:
            status()
        output = buf.getvalue()

        assert "Status: offline" in output
        assert "Server:" not in output


class TestPIDFile:
    """PID 文件测试"""

    def test_pid_file_uses_tempdir(self):
        import tempfile
        from main import PID_FILE

        tmpdir = tempfile.gettempdir()
        assert PID_FILE.startswith(tmpdir)

    def test_check_pid_file_writes(self):
        from main import check_pid_file, cleanup_pid_file, PID_FILE

        try:
            if Path(PID_FILE).exists():
                Path(PID_FILE).unlink()
            check_pid_file()
            assert Path(PID_FILE).exists()
            assert str(os.getpid()) in Path(PID_FILE).read_text()
        finally:
            cleanup_pid_file()

    def test_cleanup_pid_file_removes(self):
        from main import check_pid_file, cleanup_pid_file, PID_FILE

        check_pid_file()
        assert Path(PID_FILE).exists()
        cleanup_pid_file()
        assert not Path(PID_FILE).exists()

    def test_check_pid_file_duplicate_detection(self):
        from main import check_pid_file, cleanup_pid_file, PID_FILE

        try:
            if Path(PID_FILE).exists():
                Path(PID_FILE).unlink()
            check_pid_file()
            with patch("sys.exit") as mock_exit, patch("builtins.print"):
                check_pid_file()
            mock_exit.assert_not_called()
        finally:
            cleanup_pid_file()


class TestInputWithDefault:
    """input_with_default 测试"""

    def test_returns_value_when_entered(self):
        from main import input_with_default

        with patch("builtins.input", return_value="my_value"):
            result = input_with_default("Enter", "default_value")
        assert result == "my_value"

    def test_returns_default_when_empty(self):
        from main import input_with_default

        with patch("builtins.input", return_value=""):
            result = input_with_default("Enter", "default_value")
        assert result == "default_value"

    def test_returns_default_when_whitespace_only(self):
        from main import input_with_default

        with patch("builtins.input", return_value="   "):
            result = input_with_default("Enter", "default_value")
        assert result == "default_value"


class TestCLISession:
    """CLI session 管理测试"""

    def test_create_cli_session(self):
        from cli import create_cli_session

        with patch("cli.load_settings", return_value={"default_agent_id": "my_agent"}):
            sid = create_cli_session()
        try:
            assert sid.startswith("cli_")
            assert len(sid) == len("cli_") + 8
            sessions = _load()
            assert sid in sessions
            # CLI 会话应绑定 settings.json 的 default_agent_id，而非硬编码 main_agent
            assert sessions[sid]["agent_id"] == "my_agent"
        finally:
            _cleanup_session(sid)

    def test_create_cli_session_falls_back_to_main_agent(self):
        """settings 无 default_agent_id 时回退 main_agent"""
        from cli import create_cli_session

        with patch("cli.load_settings", return_value={}):
            sid = create_cli_session()
        try:
            sessions = _load()
            assert sessions[sid]["agent_id"] == "main_agent"
        finally:
            _cleanup_session(sid)

    def test_create_multiple_cli_sessions_unique(self):
        from cli import create_cli_session

        sid1 = create_cli_session()
        sid2 = create_cli_session()
        sid3 = create_cli_session()
        try:
            assert sid1 != sid2
            assert sid2 != sid3
            assert sid1 != sid3
        finally:
            for sid in [sid1, sid2, sid3]:
                _cleanup_session(sid)


class TestCLICommands:
    """handle_cli_command 测试"""

    def setup_method(self):
        from cli import create_cli_session
        self.session_id = create_cli_session()

    def teardown_method(self):
        _cleanup_session(self.session_id)

    def test_new_command(self):
        from cli import handle_cli_command

        is_cmd, new_sid = handle_cli_command("/new", self.session_id)
        assert is_cmd is True
        assert new_sid != self.session_id
        assert new_sid.startswith("cli_")
        _cleanup_session(new_sid)

    def test_clear_command(self):
        from cli import handle_cli_command

        is_cmd, new_sid = handle_cli_command("/clear", self.session_id)
        assert is_cmd is True
        assert new_sid != self.session_id
        assert new_sid.startswith("cli_")
        old_session_dir = get_sessions_dir() / self.session_id
        assert not old_session_dir.exists()
        _cleanup_session(new_sid)

    def test_session_switch_command(self):
        from cli import handle_cli_command

        is_cmd, new_sid = handle_cli_command(
            f"/session {self.session_id}", "other_session"
        )
        assert is_cmd is True
        assert new_sid == "other_session"

    def test_session_not_found(self):
        from cli import handle_cli_command

        with patch("builtins.print"):
            is_cmd, new_sid = handle_cli_command(
                "/session nonexistent_id", self.session_id
            )
        assert is_cmd is True
        assert new_sid == self.session_id

    def test_session_list_command(self):
        from cli import handle_cli_command

        with patch("builtins.print"):
            is_cmd, new_sid = handle_cli_command("/session_list", self.session_id)
        assert is_cmd is True
        assert new_sid == self.session_id

    def test_normal_text_not_a_command(self):
        from cli import handle_cli_command

        is_cmd, new_sid = handle_cli_command("Hello, how are you?", self.session_id)
        assert is_cmd is False
        assert new_sid == self.session_id

    def test_handle_cli_command_is_not_async(self):
        import inspect
        from cli import handle_cli_command

        assert not inspect.iscoroutinefunction(handle_cli_command)
