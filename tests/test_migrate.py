"""迁移命令单元测试

覆盖 parse_env_file、build_config_from_env、check_migration_needed
以及 migrate CLI 命令的主要功能。
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from driving.commands.migrate import (
    build_config_from_env,
    check_migration_needed,
    parse_env_file,
)
from driving.cli import cli
from driving.utils.config_manager import CONFIG_FILE_NAME


# ==================== parse_env_file 测试 ====================


class TestParseEnvFile:
    """parse_env_file 函数测试"""

    def test_parses_basic_key_value(self, tmp_path):
        """正常解析 KEY=VALUE 格式"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text("DRIVING_REPO_URL=https://github.com/user/repo\n", encoding="utf-8")

        result = parse_env_file(env_file)
        assert result["DRIVING_REPO_URL"] == "https://github.com/user/repo"

    def test_ignores_comment_lines(self, tmp_path):
        """忽略注释行"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text(
            "# 这是注释\nDRIVING_REPO_URL=https://github.com/user/repo\n",
            encoding="utf-8",
        )

        result = parse_env_file(env_file)
        assert len(result) == 1
        assert "DRIVING_REPO_URL" in result

    def test_ignores_empty_lines(self, tmp_path):
        """忽略空行"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text(
            "\nDRIVING_REPO_URL=https://github.com/user/repo\n\n",
            encoding="utf-8",
        )

        result = parse_env_file(env_file)
        assert len(result) == 1

    def test_parses_multiple_keys(self, tmp_path):
        """解析多个配置项"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text(
            "DRIVING_REPO_URL=https://github.com/user/repo\n"
            "DRIVING_DEFAULT_COMMIT_MESSAGE=update by driving\n"
            "DRIVING_UPDATE_VERSION_URL=https://example.com/version.json\n",
            encoding="utf-8",
        )

        result = parse_env_file(env_file)
        assert len(result) == 3
        assert result["DRIVING_DEFAULT_COMMIT_MESSAGE"] == "update by driving"
        assert result["DRIVING_UPDATE_VERSION_URL"] == "https://example.com/version.json"

    def test_returns_empty_dict_for_empty_file(self, tmp_path):
        """空文件返回空字典"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text("", encoding="utf-8")

        result = parse_env_file(env_file)
        assert result == {}

    def test_returns_empty_dict_for_comments_only(self, tmp_path):
        """仅含注释的文件返回空字典"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text("# 注释1\n# 注释2\n", encoding="utf-8")

        result = parse_env_file(env_file)
        assert result == {}

    def test_value_with_equals_sign(self, tmp_path):
        """值中包含等号时，只按第一个等号分割"""
        env_file = tmp_path / ".env.driving"
        env_file.write_text("KEY=value=with=equals\n", encoding="utf-8")

        result = parse_env_file(env_file)
        assert result["KEY"] == "value=with=equals"


# ==================== build_config_from_env 测试 ====================


class TestBuildConfigFromEnv:
    """build_config_from_env 函数测试"""

    def test_migrates_repo_url(self):
        """DRIVING_REPO_URL 正确迁移为 repos[0]"""
        env_vars = {"DRIVING_REPO_URL": "https://github.com/user/driving"}
        config, migrated, non_migratable = build_config_from_env(env_vars)

        assert len(config.repos) == 1
        assert config.repos[0].url == "https://github.com/user/driving"
        assert config.repos[0].type == "remote"
        assert config.repos[0].name == "driving"  # 从 URL 推断
        assert config.repos[0].path == "ai-driving/driving"

    def test_migrates_commit_message(self):
        """DRIVING_DEFAULT_COMMIT_MESSAGE 正确迁移"""
        env_vars = {"DRIVING_DEFAULT_COMMIT_MESSAGE": "my custom message"}
        config, migrated, _ = build_config_from_env(env_vars)

        assert config.default_commit_message == "my custom message"
        assert any("DRIVING_DEFAULT_COMMIT_MESSAGE" in k for k, _ in migrated)

    def test_migrates_update_version_url(self):
        """DRIVING_UPDATE_VERSION_URL 正确迁移"""
        env_vars = {"DRIVING_UPDATE_VERSION_URL": "https://example.com/version.json"}
        config, migrated, _ = build_config_from_env(env_vars)

        assert config.update_version_url == "https://example.com/version.json"
        assert any("DRIVING_UPDATE_VERSION_URL" in k for k, _ in migrated)

    def test_uses_defaults_when_keys_missing(self):
        """缺少配置项时使用默认值"""
        config, migrated, _ = build_config_from_env({})

        assert config.repos == []
        assert config.default_commit_message == "update by driving"
        assert config.version == "2"

    def test_detects_non_migratable_local_mode(self):
        """检测到 DRIVING_LOCAL_MODE 并列为无法迁移"""
        env_vars = {"DRIVING_LOCAL_MODE": "true"}
        _, _, non_migratable = build_config_from_env(env_vars)

        keys = [k for k, _ in non_migratable]
        assert "DRIVING_LOCAL_MODE" in keys

    def test_detects_unknown_keys_as_non_migratable(self):
        """未知配置项列为无法迁移"""
        env_vars = {"UNKNOWN_KEY": "some_value"}
        _, _, non_migratable = build_config_from_env(env_vars)

        keys = [k for k, _ in non_migratable]
        assert "UNKNOWN_KEY" in keys

    def test_migrated_list_contains_repo_url(self):
        """已迁移列表包含 DRIVING_REPO_URL"""
        env_vars = {"DRIVING_REPO_URL": "https://github.com/user/repo"}
        _, migrated, _ = build_config_from_env(env_vars)

        keys = [k for k, _ in migrated]
        assert "DRIVING_REPO_URL" in keys

    def test_infers_repo_name_from_url(self):
        """从 URL 正确推断仓库名称"""
        env_vars = {"DRIVING_REPO_URL": "https://git.internal.taqu.cn/android/driving"}
        config, _, _ = build_config_from_env(env_vars)

        assert config.repos[0].name == "driving"

    def test_full_migration(self):
        """完整迁移场景：所有可迁移字段都存在"""
        env_vars = {
            "DRIVING_REPO_URL": "https://github.com/user/my-repo",
            "DRIVING_DEFAULT_COMMIT_MESSAGE": "custom commit",
            "DRIVING_UPDATE_VERSION_URL": "https://example.com/v.json",
        }
        config, migrated, non_migratable = build_config_from_env(env_vars)

        assert len(config.repos) == 1
        assert config.repos[0].name == "my-repo"
        assert config.default_commit_message == "custom commit"
        assert config.update_version_url == "https://example.com/v.json"
        assert len(migrated) == 3
        assert non_migratable == []


# ==================== check_migration_needed 测试 ====================


class TestCheckMigrationNeeded:
    """check_migration_needed 函数测试"""

    def test_returns_true_when_env_exists_no_config(self, tmp_path):
        """.env.driving 存在但 driving.config.json 不存在时返回 True"""
        (tmp_path / ".env.driving").write_text("DRIVING_REPO_URL=https://example.com/repo\n")

        assert check_migration_needed(tmp_path) is True

    def test_returns_false_when_both_exist(self, tmp_path):
        """两个文件都存在时返回 False"""
        (tmp_path / ".env.driving").write_text("DRIVING_REPO_URL=https://example.com/repo\n")
        (tmp_path / CONFIG_FILE_NAME).write_text("{}", encoding="utf-8")

        assert check_migration_needed(tmp_path) is False

    def test_returns_false_when_env_missing(self, tmp_path):
        """.env.driving 不存在时返回 False"""
        assert check_migration_needed(tmp_path) is False

    def test_returns_false_when_both_missing(self, tmp_path):
        """两个文件都不存在时返回 False"""
        assert check_migration_needed(tmp_path) is False


# ==================== migrate CLI 命令测试 ====================


class TestMigrateCommand:
    """migrate CLI 命令集成测试"""

    def _make_env_file(self, tmp_path: Path, content: str) -> None:
        """在 tmp_path 创建 .env.driving 文件"""
        (tmp_path / ".env.driving").write_text(content, encoding="utf-8")

    def test_migrate_creates_config_file(self, tmp_path, monkeypatch):
        """migrate 命令成功创建 driving.config.json"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(
            tmp_path,
            "DRIVING_REPO_URL=https://github.com/user/driving\n"
            "DRIVING_UPDATE_VERSION_URL=https://example.com/version.json\n",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate"])

        assert result.exit_code == 0
        assert (tmp_path / CONFIG_FILE_NAME).exists()

    def test_migrate_config_content_correct(self, tmp_path, monkeypatch):
        """migrate 命令生成的配置内容正确"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(
            tmp_path,
            "DRIVING_REPO_URL=https://github.com/user/my-repo\n"
            "DRIVING_DEFAULT_COMMIT_MESSAGE=custom commit\n",
        )

        runner = CliRunner()
        runner.invoke(cli, ["migrate"])

        config_data = json.loads((tmp_path / CONFIG_FILE_NAME).read_text(encoding="utf-8"))
        assert config_data["version"] == "2"
        assert len(config_data["repos"]) == 1
        assert config_data["repos"][0]["name"] == "my-repo"
        assert config_data["repos"][0]["type"] == "remote"
        assert config_data["default_commit_message"] == "custom commit"

    def test_migrate_no_env_file(self, tmp_path, monkeypatch):
        """没有 .env.driving 时提示无需迁移"""
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate"])

        assert result.exit_code == 0
        assert "无需迁移" in result.output
        assert not (tmp_path / CONFIG_FILE_NAME).exists()

    def test_migrate_dry_run_does_not_write(self, tmp_path, monkeypatch):
        """dry-run 模式不写入文件"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(tmp_path, "DRIVING_REPO_URL=https://github.com/user/repo\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate", "--dry-run"])

        assert result.exit_code == 0
        assert not (tmp_path / CONFIG_FILE_NAME).exists()
        assert "dry-run" in result.output

    def test_migrate_shows_non_migratable_keys(self, tmp_path, monkeypatch):
        """迁移报告中列出无法自动迁移的配置项"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(
            tmp_path,
            "DRIVING_REPO_URL=https://github.com/user/repo\n"
            "DRIVING_LOCAL_MODE=true\n",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate"])

        assert "DRIVING_LOCAL_MODE" in result.output

    def test_migrate_does_not_delete_env_file(self, tmp_path, monkeypatch):
        """迁移完成后不自动删除 .env.driving"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(tmp_path, "DRIVING_REPO_URL=https://github.com/user/repo\n")

        runner = CliRunner()
        runner.invoke(cli, ["migrate"])

        # .env.driving 应仍然存在
        assert (tmp_path / ".env.driving").exists()

    def test_migrate_prompts_hint_to_delete_env(self, tmp_path, monkeypatch):
        """迁移完成后提示用户可手动删除 .env.driving"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(tmp_path, "DRIVING_REPO_URL=https://github.com/user/repo\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate"])

        # 应提示用户可以删除
        assert ".env.driving" in result.output
        assert "删除" in result.output

    def test_migrate_existing_config_aborts_without_confirm(self, tmp_path, monkeypatch):
        """driving.config.json 已存在时，拒绝覆盖则取消迁移"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(tmp_path, "DRIVING_REPO_URL=https://github.com/user/repo\n")
        # 预先创建配置文件
        (tmp_path / CONFIG_FILE_NAME).write_text('{"version":"2","repos":[],"default_commit_message":"old","update_version_url":""}')

        runner = CliRunner()
        # 输入 "n" 拒绝覆盖
        result = runner.invoke(cli, ["migrate"], input="n\n")

        assert result.exit_code == 0
        assert "取消" in result.output
        # 原配置文件内容不变
        data = json.loads((tmp_path / CONFIG_FILE_NAME).read_text())
        assert data["default_commit_message"] == "old"

    def test_migrate_shows_migrated_keys(self, tmp_path, monkeypatch):
        """迁移报告中展示已迁移的配置项"""
        monkeypatch.chdir(tmp_path)
        self._make_env_file(
            tmp_path,
            "DRIVING_REPO_URL=https://github.com/user/repo\n"
            "DRIVING_UPDATE_VERSION_URL=https://example.com/v.json\n",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["migrate"])

        assert "DRIVING_REPO_URL" in result.output
        assert "DRIVING_UPDATE_VERSION_URL" in result.output
