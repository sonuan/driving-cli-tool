"""update 命令单元测试

覆盖核心场景：
- ~/.driving-cli/driving 存在时优先使用（无需 sudo）
- ~/.driving-cli/driving 不存在时回退到 which driving（兼容旧方案）
- 有写权限时直接安装（无需 sudo）
- 无写权限时自动 fallback 到 sudo
- sudo 执行失败时正确报错
- --check 模式仅检查不安装
- 已是最新版本时跳过安装
"""

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from driving_cli.commands.update import (
    compare_versions,
    fetch_version_info,
    get_current_version,
    update,
)


# ==================== 测试夹具 ====================

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def version_info():
    """模拟服务器返回的版本信息"""
    return {
        "version": "9.9.9",
        "download_url": "http://example.com/driving",
        "changelog": ["修复若干问题", "新增功能 X"],
    }


@pytest.fixture
def fake_binary(tmp_path):
    """创建一个足够大的假二进制文件（>1KB）"""
    binary = tmp_path / "driving.tmp"
    binary.write_bytes(b"x" * 2048)
    return binary


# ==================== compare_versions 测试 ====================

class TestCompareVersions:
    def test_older(self):
        assert compare_versions("1.0.0", "1.1.0") == -1

    def test_equal(self):
        assert compare_versions("1.2.3", "1.2.3") == 0

    def test_newer(self):
        assert compare_versions("2.0.0", "1.9.9") == 1

    def test_different_length(self):
        assert compare_versions("1.0", "1.0.1") == -1

    def test_invalid_falls_back_to_equal(self):
        assert compare_versions("invalid", "1.0.0") == 0


# ==================== 安装权限逻辑测试 ====================

class TestInstallPermission:
    """测试有/无写权限时的 fallback 行为"""

    def _invoke_update(self, runner, version_info, tmp_path, monkeypatch,
                       permission_error=False, sudo_returncode=0):
        """
        通用辅助：mock 下载 + 安装，触发 update 命令。

        Args:
            permission_error: _do_install 是否抛 PermissionError
            sudo_returncode:  sudo 子进程的返回码
        """
        fake_exe = str(tmp_path / "driving")
        Path(fake_exe).write_bytes(b"old")

        # mock fetch_version_info
        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("subprocess.run") as mock_subprocess, \
             patch("urllib.request.urlopen") as mock_urlopen, \
             patch("tempfile.mkstemp") as mock_mkstemp, \
             patch("os.fdopen"), \
             patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("shutil.move") as mock_move, \
             patch("os.unlink") as mock_unlink, \
             patch("os.chmod") as mock_chmod:

            # which driving → 返回 fake_exe
            which_result = MagicMock()
            which_result.returncode = 0
            which_result.stdout = fake_exe + "\n"

            sudo_result = MagicMock()
            sudo_result.returncode = sudo_returncode

            def subprocess_side_effect(args, **kwargs):
                if args[0] == "which":
                    return which_result
                return sudo_result

            mock_subprocess.side_effect = subprocess_side_effect

            # mock 下载响应
            mock_response = MagicMock()
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.headers = {"Content-Length": "2048"}
            mock_response.read.side_effect = [b"x" * 2048, b""]
            mock_urlopen.return_value = mock_response

            # mock tempfile.mkstemp → 返回假路径
            tmp_bin = str(tmp_path / "driving.tmp")
            mock_mkstemp.return_value = (3, tmp_bin)

            # 按需让 shutil.move 抛 PermissionError（模拟第一次无权限）
            if permission_error:
                # os.unlink 在 _do_install 中先被调用，不报错；
                # shutil.move 抛 PermissionError
                mock_unlink.return_value = None
                mock_move.side_effect = PermissionError("Permission denied")
            else:
                mock_unlink.return_value = None
                mock_move.return_value = None

            result = runner.invoke(update, ["--yes"])
            return result, mock_subprocess, mock_move, mock_unlink

    def test_install_without_permission_error(self, runner, version_info, tmp_path):
        """有写权限时直接安装，不调用 sudo"""
        result, mock_subprocess, mock_move, _ = self._invoke_update(
            runner, version_info, tmp_path, None, permission_error=False
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output

        # sudo sh -c ... 不应被调用
        sudo_calls = [c for c in mock_subprocess.call_args_list
                      if c.args and c.args[0] and c.args[0][0] == "sudo"]
        assert len(sudo_calls) == 0

    def test_install_fallback_to_sudo_on_permission_error(self, runner, version_info, tmp_path):
        """无写权限时自动 fallback 到 sudo，且 sudo 成功"""
        result, mock_subprocess, mock_move, _ = self._invoke_update(
            runner, version_info, tmp_path, None,
            permission_error=True, sudo_returncode=0
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output

        # 确认调用了 sudo sh -c
        sudo_calls = [c for c in mock_subprocess.call_args_list
                      if c.args and c.args[0] and c.args[0][0] == "sudo"]
        assert len(sudo_calls) == 1
        assert "sh" in sudo_calls[0].args[0]

    def test_install_sudo_fails(self, runner, version_info, tmp_path):
        """sudo 执行失败时报错"""
        result, _, _, _ = self._invoke_update(
            runner, version_info, tmp_path, None,
            permission_error=True, sudo_returncode=1
        )
        assert result.exit_code == 0  # click 命令本身不崩溃
        assert "安装失败" in result.output


# ==================== --check 模式测试 ====================

class TestCheckMode:
    def test_check_shows_new_version(self, runner, version_info):
        """--check 发现新版本时只打印，不安装"""
        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"):
            result = runner.invoke(update, ["--check"])

        assert result.exit_code == 0
        assert "9.9.9" in result.output
        # 不应触发下载
        assert "下载" not in result.output

    def test_check_already_latest(self, runner, version_info):
        """--check 已是最新版本"""
        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="9.9.9"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"):
            result = runner.invoke(update, ["--check"])

        assert result.exit_code == 0
        assert "最新版本" in result.output


# ==================== 已是最新版本测试 ====================

class TestAlreadyLatest:
    def test_skips_install_when_up_to_date(self, runner, version_info):
        """当前版本 >= 最新版本时，不下载不安装"""
        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="9.9.9"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("urllib.request.urlopen") as mock_urlopen:
            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        assert "最新版本" in result.output
        mock_urlopen.assert_not_called()


# ==================== 安装路径选择测试 ====================

class TestInstallPathSelection:
    """测试 ~/.driving-cli/driving 优先逻辑及旧方案兼容回退"""

    def _common_mocks(self, version_info, tmp_path):
        """返回下载相关的公共 mock context managers 列表（不含路径相关 mock）"""
        return [
            patch("driving_cli.commands.update.fetch_version_info", return_value=version_info),
            patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"),
            patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"),
            patch("urllib.request.urlopen", **self._make_urlopen_attrs()),
            patch("tempfile.mkstemp", return_value=(3, str(tmp_path / "driving.tmp"))),
            patch("os.fdopen"),
            patch("os.fsync"),
            patch("os.path.getsize", return_value=2048),
            patch("os.unlink"),
            patch("os.makedirs"),
            patch("shutil.move"),
            patch("os.chmod"),
        ]

    def _make_urlopen_attrs(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.headers = {"Content-Length": "2048"}
        mock_resp.read.side_effect = [b"x" * 2048, b""]
        return {"return_value": mock_resp}

    def test_prefers_user_install_dir_when_exists(self, runner, version_info, tmp_path):
        """~/.driving-cli/driving 存在时，直接用该路径更新，不调用 which"""
        user_driving = tmp_path / ".driving-cli" / "driving"
        user_driving.parent.mkdir(parents=True)
        user_driving.write_bytes(b"old binary")

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("urllib.request.urlopen", **self._make_urlopen_attrs()), \
             patch("tempfile.mkstemp", return_value=(3, str(tmp_path / "driving.tmp"))), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.unlink"), patch("os.makedirs"), \
             patch("shutil.move"), patch("os.chmod"), \
             patch("subprocess.run") as mock_sub:

            # which 不应被调用
            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        assert "更新成功" in result.output

        which_calls = [c for c in mock_sub.call_args_list
                       if c.args and c.args[0] and c.args[0][0] == "which"]
        assert len(which_calls) == 0, "~/.driving-cli/driving 存在时不应调用 which"

    def test_falls_back_to_which_when_user_dir_absent(self, runner, version_info, tmp_path):
        """~/.driving-cli/driving 不存在时，回退到 which driving"""
        fake_exe = str(tmp_path / "driving")
        Path(fake_exe).write_bytes(b"old")

        which_result = MagicMock()
        which_result.returncode = 0
        which_result.stdout = fake_exe + "\n"

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("urllib.request.urlopen", **self._make_urlopen_attrs()), \
             patch("tempfile.mkstemp", return_value=(3, str(tmp_path / "driving.tmp"))), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.unlink"), patch("os.makedirs"), \
             patch("shutil.move"), patch("os.chmod"), \
             patch("subprocess.run", return_value=which_result) as mock_sub:

            # ~/.driving-cli 目录不存在（tmp_path 下没有 .driving-cli/driving）
            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        assert "更新成功" in result.output

        which_calls = [c for c in mock_sub.call_args_list
                       if c.args and c.args[0] and c.args[0][0] == "which"]
        assert len(which_calls) == 1, "~/.driving-cli/driving 不存在时应调用 which"
