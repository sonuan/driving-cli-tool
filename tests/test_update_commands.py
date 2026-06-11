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
from unittest.mock import MagicMock, patch

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


def _make_urlopen_mock():
    """构造一个模拟下载响应的 urlopen mock"""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.headers = {"Content-Length": "2048"}
    mock_resp.read.side_effect = [b"x" * 2048, b""]
    return mock_resp


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
    """测试有/无写权限时的 fallback 行为。
    使用真实 tmp_path，让代码自然走 ~/.driving-cli 路径逻辑。
    """

    def _invoke_update(self, runner, version_info, tmp_path,
                       permission_error=False, sudo_returncode=0):
        """
        通用辅助：在 tmp_path 下模拟 ~/.driving-cli/driving 已存在，
        mock 下载 + os.replace，触发 update 命令。
        """
        # 模拟已通过新方式安装
        user_dir = tmp_path / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"old")

        # 临时文件也放在同目录（与生产代码逻辑一致）
        tmp_bin = str(user_dir / "driving.tmp")

        which_result = MagicMock(returncode=0, stdout=str(user_dir / "driving") + "\n")
        sudo_result = MagicMock(returncode=sudo_returncode)

        def subprocess_side_effect(args, **kwargs):
            if args[0] == "which":
                return which_result
            return sudo_result

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=subprocess_side_effect) as mock_sub, \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), \
             patch("os.replace") as mock_replace, \
             patch("os.chmod"):

            if permission_error:
                mock_replace.side_effect = PermissionError("Permission denied")

            result = runner.invoke(update, ["--yes"])
            return result, mock_sub, mock_replace

    def test_install_without_permission_error(self, runner, version_info, tmp_path):
        """有写权限时直接安装，不调用 sudo"""
        result, mock_sub, mock_replace = self._invoke_update(
            runner, version_info, tmp_path, permission_error=False
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output

        sudo_calls = [c for c in mock_sub.call_args_list
                      if c.args and c.args[0] and c.args[0][0] == "sudo"]
        assert len(sudo_calls) == 0

    def test_install_fallback_to_sudo_on_permission_error(self, runner, version_info, tmp_path):
        """无写权限时自动 fallback 到 sudo，且 sudo 成功"""
        result, mock_sub, _ = self._invoke_update(
            runner, version_info, tmp_path,
            permission_error=True, sudo_returncode=0
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output

        sudo_calls = [c for c in mock_sub.call_args_list
                      if c.args and c.args[0] and c.args[0][0] == "sudo"]
        assert len(sudo_calls) == 1
        assert "sh" in sudo_calls[0].args[0]

    def test_install_sudo_fails(self, runner, version_info, tmp_path):
        """sudo 执行失败时报错"""
        result, _, _ = self._invoke_update(
            runner, version_info, tmp_path,
            permission_error=True, sudo_returncode=1
        )
        assert result.exit_code == 0
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

    def _base_patches(self, version_info, tmp_path, tmp_bin):
        """公共 patch 列表（不含路径和 subprocess 相关）"""
        return [
            patch("driving_cli.commands.update.fetch_version_info", return_value=version_info),
            patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"),
            patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"),
            patch("urllib.request.urlopen", return_value=_make_urlopen_mock()),
            patch("tempfile.mkstemp", return_value=(3, tmp_bin)),
            patch("os.fdopen"),
            patch("os.fsync"),
            patch("os.path.getsize", return_value=2048),
            patch("os.makedirs"),
            patch("os.replace"),
            patch("os.chmod"),
        ]

    def test_prefers_user_install_dir_when_exists(self, runner, version_info, tmp_path):
        """~/.driving-cli/driving 存在时，直接用该路径更新，不调用 which"""
        user_dir = tmp_path / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"old binary")
        tmp_bin = str(user_dir / "driving.tmp")

        patches = self._base_patches(version_info, tmp_path, tmp_bin) + [
            patch("pathlib.Path.home", return_value=tmp_path),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], \
             patch("subprocess.run") as mock_sub:

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
        tmp_bin = str(tmp_path / "driving.tmp")

        which_result = MagicMock(returncode=0, stdout=fake_exe + "\n")

        patches = self._base_patches(version_info, tmp_path, tmp_bin) + [
            patch("pathlib.Path.home", return_value=tmp_path),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], \
             patch("subprocess.run", return_value=which_result) as mock_sub:

            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        assert "更新成功" in result.output

        which_calls = [c for c in mock_sub.call_args_list
                       if c.args and c.args[0] and c.args[0][0] == "which"]
        assert len(which_calls) == 1, "~/.driving-cli/driving 不存在时应调用 which"


# ==================== 旧安装方式迁移测试 ====================

class TestMigrateToUserDir:
    """测试旧安装方式（/usr/local/bin/driving 真实文件）迁移到 ~/.driving-cli/driving"""

    def _invoke_with_old_install(self, runner, version_info, tmp_path,
                                  symlink_ok=True, sudo_returncode=0):
        """
        模拟旧安装方式：~/.driving-cli/driving 不存在，
        which 指向 tmp_path/usr/local/bin/driving（真实文件，非符号链接）。
        """
        # 旧安装位置：真实文件
        old_bin_dir = tmp_path / "usr" / "local" / "bin"
        old_bin_dir.mkdir(parents=True)
        old_bin = old_bin_dir / "driving"
        old_bin.write_bytes(b"old binary")

        # 新安装目录（迁移目标）
        user_dir = tmp_path / ".driving-cli"
        new_bin = user_dir / "driving"
        tmp_bin = str(user_dir / "driving.tmp")  # 同目录临时文件

        symlink_path = tmp_path / "usr" / "local" / "bin" / "driving_link"  # 用于 mock

        which_result = MagicMock(returncode=0, stdout=str(old_bin) + "\n")
        sudo_result = MagicMock(returncode=sudo_returncode)

        def subprocess_side_effect(args, **kwargs):
            if args[0] == "which":
                return which_result
            return sudo_result

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), \
             patch("os.replace"), patch("os.chmod"), \
             patch("subprocess.run", side_effect=subprocess_side_effect) as mock_sub, \
             patch("pathlib.Path.is_symlink", return_value=False), \
             patch("pathlib.Path.symlink_to",
                   side_effect=None if symlink_ok else PermissionError("denied")), \
             patch("pathlib.Path.unlink"):

            result = runner.invoke(update, ["--yes"])
            return result, mock_sub

    def test_检测到旧安装方式时触发迁移提示(self, runner, version_info, tmp_path):
        """旧安装方式时输出迁移提示"""
        result, _ = self._invoke_with_old_install(runner, version_info, tmp_path)
        assert result.exit_code == 0
        assert "迁移" in result.output

    def test_迁移成功输出成功提示(self, runner, version_info, tmp_path):
        """符号链接创建成功时输出迁移成功提示"""
        result, _ = self._invoke_with_old_install(
            runner, version_info, tmp_path, symlink_ok=True
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output

    def test_符号链接无权限时调用sudo(self, runner, version_info, tmp_path):
        """符号链接创建失败时自动调用 sudo"""
        result, mock_sub = self._invoke_with_old_install(
            runner, version_info, tmp_path, symlink_ok=False, sudo_returncode=0
        )
        assert result.exit_code == 0
        sudo_calls = [c for c in mock_sub.call_args_list
                      if c.args and c.args[0] and c.args[0][0] == "sudo"]
        assert len(sudo_calls) == 1

    def test_新安装方式不触发迁移(self, runner, version_info, tmp_path):
        """~/.driving-cli/driving 已存在时不触发迁移"""
        user_dir = tmp_path / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"existing")
        tmp_bin = str(user_dir / "driving.tmp")

        which_result = MagicMock(returncode=0, stdout=str(user_dir / "driving") + "\n")

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), patch("os.replace"), patch("os.chmod"), \
             patch("subprocess.run", return_value=which_result):

            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        assert "已迁移到新安装方式" not in result.output
        assert "更新成功" in result.output


# ==================== sudo 用户 home 还原测试 ====================

class TestSudoUserHome:
    """测试 sudo 执行时通过 SUDO_USER 还原真实用户 home"""

    def _invoke_with_sudo_user(self, runner, version_info, tmp_path, sudo_user="alice"):
        """模拟 SUDO_USER 环境变量存在的场景"""
        # 模拟真实用户目录
        user_home = tmp_path / "home" / sudo_user
        user_dir = user_home / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"old binary")
        tmp_bin = str(user_dir / "driving.tmp")

        import pwd as _pwd_mod
        pw_entry = MagicMock()
        pw_entry.pw_dir = str(user_home)

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch.dict("os.environ", {"SUDO_USER": sudo_user}), \
             patch("pwd.getpwnam", return_value=pw_entry), \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), \
             patch("os.replace"), patch("os.chmod"), \
             patch("subprocess.run") as mock_sub:

            result = runner.invoke(update, ["--yes"])
            return result, mock_sub, str(user_dir)

    def test_sudo_user时使用真实用户home(self, runner, version_info, tmp_path):
        """SUDO_USER 存在时安装路径应在真实用户目录而非 /root"""
        result, _, user_dir = self._invoke_with_sudo_user(
            runner, version_info, tmp_path
        )
        assert result.exit_code == 0
        assert "更新成功" in result.output
        # 安装位置应包含真实用户目录
        assert "home/alice/.driving-cli" in result.output

    def test_sudo_user时安装完成后执行chown(self, runner, version_info, tmp_path):
        """sudo 安装完成后应执行 chown 归还所有权"""
        result, mock_sub, user_dir = self._invoke_with_sudo_user(
            runner, version_info, tmp_path, sudo_user="alice"
        )
        assert result.exit_code == 0

        chown_calls = [c for c in mock_sub.call_args_list
                       if c.args and c.args[0] and c.args[0][0] == "chown"]
        assert len(chown_calls) == 1
        chown_args = chown_calls[0].args[0]
        assert "alice" in chown_args

    def test_无sudo_user时不执行chown(self, runner, version_info, tmp_path):
        """无 SUDO_USER 时不执行 chown"""
        user_dir = tmp_path / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"old binary")
        tmp_bin = str(user_dir / "driving.tmp")

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch.dict("os.environ", {}, clear=True), \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), patch("os.replace"), patch("os.chmod"), \
             patch("subprocess.run") as mock_sub:

            result = runner.invoke(update, ["--yes"])

        assert result.exit_code == 0
        chown_calls = [c for c in mock_sub.call_args_list
                       if c.args and c.args[0] and c.args[0][0] == "chown"]
        assert len(chown_calls) == 0


# ==================== op_reporter 集成：update_completed ====================

class TestUpdateOpReporter:
    """driving update 成功后的 op_reporter 上报行为"""

    def _invoke_update_success(self, runner, version_info, tmp_path):
        """辅助：模拟 update 安装成功的最小场景"""
        user_dir = tmp_path / ".driving-cli"
        user_dir.mkdir(parents=True)
        (user_dir / "driving").write_bytes(b"old")
        tmp_bin = str(user_dir / "driving.tmp")

        which_result = MagicMock(returncode=0, stdout=str(user_dir / "driving") + "\n")

        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="1.0.0"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("pathlib.Path.home", return_value=tmp_path), \
             patch("subprocess.run", return_value=which_result), \
             patch("urllib.request.urlopen", return_value=_make_urlopen_mock()), \
             patch("tempfile.mkstemp", return_value=(3, tmp_bin)), \
             patch("os.fdopen"), patch("os.fsync"), \
             patch("os.path.getsize", return_value=2048), \
             patch("os.makedirs"), \
             patch("os.replace"), patch("os.chmod"):
            return runner.invoke(update, ["--yes"])

    def test_更新成功后调用report_op_event(self, runner, version_info, tmp_path):
        """update 安装成功后应上报 update_completed"""
        with patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://hook.example.com"):
            result = self._invoke_update_success(runner, version_info, tmp_path)
        assert result.exit_code == 0
        assert "更新成功" in result.output
        mock_async.assert_called_once()
        _, payload = mock_async.call_args.args
        assert payload["operation"] == "update_completed"
        # from_version / to_version 现在在 extra 嵌套对象里
        assert payload.get("extra", {}).get("from_version") == "1.0.0"
        assert payload.get("extra", {}).get("to_version") == "9.9.9"

    def test_更新成功时cli_version传新版本(self, runner, version_info, tmp_path):
        """update_completed 上报时 cli_version 应为更新后的新版本"""
        with patch("driving_cli.utils.op_reporter.report_async") as mock_async, \
             patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://hook.example.com"):
            self._invoke_update_success(runner, version_info, tmp_path)
        _, payload = mock_async.call_args.args
        assert payload.get("cli_version") == "9.9.9"

    def test_已是最新版本时不上报(self, runner, version_info, tmp_path):
        """当前版本已是最新时不调用 report_op_event"""
        with patch("driving_cli.commands.update.fetch_version_info", return_value=version_info), \
             patch("driving_cli.commands.update.get_current_version", return_value="9.9.9"), \
             patch("driving_cli.commands.update._get_update_version_url", return_value="http://x"), \
             patch("driving_cli.utils.op_reporter.report_async") as mock_async:
            result = runner.invoke(update, ["--yes"])
        assert "最新版本" in result.output
        mock_async.assert_not_called()

    def test_report_op_event异常不影响update流程(self, runner, version_info, tmp_path):
        """report_op_event 抛异常时不应影响 update 命令的正常输出"""
        with patch("driving_cli.utils.op_reporter.report_async", side_effect=Exception("hook err")), \
             patch("driving_cli.utils.op_reporter._get_webhook_url", return_value="https://hook.example.com"):
            result = self._invoke_update_success(runner, version_info, tmp_path)
        assert result.exit_code == 0
        assert "更新成功" in result.output
