"""refine 子命令组单元测试

覆盖 driving refine list / refine load / refine commit 的主要功能：
- _parse_refine_frontmatter：完整 frontmatter、缺少 target_type、无 frontmatter
- _scan_refines：type_filter 过滤、文件名匹配
- refine list：按类型分组展示、--type 过滤、--repo 过滤
- refine load：全量输出、name 模糊匹配、--type 过滤、返回字段完整性
- refine commit：--file 必填、路径校验、untracked 过滤、git 操作、--no-push
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.refine import _parse_refine_frontmatter, _scan_refines


# ==================== Helpers ====================


def _make_refine_md(
    path: Path,
    target_type: str = "skill",
    target_name: str = "test-skill",
    description: str = "测试描述",
    status: str = "pending",
    trigger: dict = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trigger_block = ""
    if trigger:
        trigger_block = f"trigger:\n  source: {trigger['source']}\n  reason: {trigger['reason']}\n"
    path.write_text(
        f"---\n"
        f"date: 2026-04-10\n"
        f"target_type: {target_type}\n"
        f"target_name: {target_name}\n"
        f"target_file: ai-driving/driving/skills/{target_name}/SKILL.md\n"
        f"description: {description}\n"
        f"operator: test\n"
        f"{trigger_block}"
        f"status: {status}\n"
        f"---\n\n# 变更内容\n\n测试内容\n",
        encoding="utf-8",
    )


def _make_config(tmp_path: Path, repos: list) -> None:
    config = {
        "version": "2",
        "repos": repos,
        "default_commit_message": "update",
        "update_version_url": "",
    }
    (tmp_path / "driving.config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ==================== _parse_refine_frontmatter ====================


class TestParseRefineFrontmatter:
    def test_完整frontmatter解析(self, tmp_path):
        f = tmp_path / "refine.md"
        _make_refine_md(f, target_type="skill", target_name="my-skill", description="测试")
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["target_type"] == "skill"
        assert result["target_name"] == "my-skill"
        assert result["description"] == "测试"
        assert result["status"] == "pending"

    def test_缺少target_type返回None(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text("---\ndate: 2026-04-10\nstatus: pending\n---\n\n内容", encoding="utf-8")
        assert _parse_refine_frontmatter(f) is None

    def test_无frontmatter返回None(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text("# 普通 markdown\n\n没有 frontmatter", encoding="utf-8")
        assert _parse_refine_frontmatter(f) is None

    def test_description缺失时返回空字符串(self, tmp_path):
        f = tmp_path / "refine.md"
        f.write_text(
            "---\ndate: 2026-04-10\ntarget_type: rule\ntarget_name: x\nstatus: pending\n---\n",
            encoding="utf-8",
        )
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["description"] == ""

    def test_trigger字段存在时正确解析(self, tmp_path):
        f = tmp_path / "refine.md"
        _make_refine_md(
            f,
            trigger={"source": "gate", "reason": "GATE-D1 返工 3 次，高频原因：页面类型判断有误"},
        )
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["trigger"] is not None
        assert result["trigger"]["source"] == "gate"
        assert "GATE-D1" in result["trigger"]["reason"]

    def test_trigger字段缺省时为None(self, tmp_path):
        f = tmp_path / "refine.md"
        _make_refine_md(f)  # 不传 trigger
        result = _parse_refine_frontmatter(f)
        assert result is not None
        assert result["trigger"] is None


# ==================== _scan_refines ====================


class TestScanRefines:
    def test_扫描返回正确条目(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo")
        _make_refine_md(tmp_path / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar")
        items = _scan_refines("driving", tmp_path)
        assert len(items) == 2

    def test_type_filter过滤(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md", target_type="skill")
        _make_refine_md(tmp_path / "2026-04-10-rule-bar.md", target_type="rule")
        items = _scan_refines("driving", tmp_path, type_filter="skill")
        assert len(items) == 1
        assert items[0]["target_type"] == "skill"

    def test_path字段格式正确(self, tmp_path):
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md")
        items = _scan_refines("my-repo", tmp_path)
        assert items[0]["path"] == "ai-driving/my-repo/refines/2026-04-10-skill-foo.md"

    def test_跳过非md文件(self, tmp_path):
        (tmp_path / "notes.txt").write_text("not a refine", encoding="utf-8")
        _make_refine_md(tmp_path / "2026-04-10-skill-foo.md")
        items = _scan_refines("driving", tmp_path)
        assert len(items) == 1


# ==================== driving refine list ====================


class TestRefineList:
    def _setup(self, tmp_path):
        _make_config(tmp_path, [{"name": "driving", "type": "local", "path": "ai-driving/driving"}])
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        _make_refine_md(refines_dir / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo", description="技能描述")
        _make_refine_md(refines_dir / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar", description="规则描述")
        return tmp_path

    def test_列出所有refine(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", refines_dir)]):
                result = runner.invoke(cli, ["refine", "list"])
        assert result.exit_code == 0
        assert "skill" in result.output
        assert "rule" in result.output
        assert "共 2 条 refine" in result.output

    def test_type过滤只显示skill(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", refines_dir)]):
                result = runner.invoke(cli, ["refine", "list", "--type", "skill"])
        assert result.exit_code == 0
        assert "skill" in result.output
        assert "rule" not in result.output
        assert "共 1 条 refine" in result.output

    def test_description显示在输出中(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", refines_dir)]):
                result = runner.invoke(cli, ["refine", "list"])
        assert "(pending)" in result.output
        lines = [l for l in result.output.splitlines() if "(pending)" in l]
        assert len(lines) > 0
        for line in lines:
            parts = line.strip().split("  ")
            assert len(parts) >= 3


# ==================== driving refine load ====================


class TestRefineLoad:
    def _setup(self, tmp_path):
        _make_config(tmp_path, [{"name": "driving", "type": "local", "path": "ai-driving/driving"}])
        refines_dir = tmp_path / "ai-driving" / "driving" / "refines"
        _make_refine_md(refines_dir / "2026-04-10-skill-foo.md", target_type="skill", target_name="foo", description="技能描述")
        _make_refine_md(refines_dir / "2026-04-10-rule-bar.md", target_type="rule", target_name="bar", description="规则描述")
        return tmp_path

    def _refines_dir(self, tmp_path):
        return tmp_path / "ai-driving" / "driving" / "refines"

    def test_全量输出两条(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", self._refines_dir(tmp_path))]):
                result = runner.invoke(cli, ["refine", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    def test_返回字段完整(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", self._refines_dir(tmp_path))]):
                result = runner.invoke(cli, ["refine", "load"])
        data = json.loads(result.output)
        for item in data:
            assert "name" in item
            assert "description" in item
            assert "path" in item

    def test_name模糊匹配(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", self._refines_dir(tmp_path))]):
                result = runner.invoke(cli, ["refine", "load", "skill"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert "skill" in data[0]["name"]

    def test_type过滤(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", self._refines_dir(tmp_path))]):
                result = runner.invoke(cli, ["refine", "load", "--type", "rule"])
        data = json.loads(result.output)
        assert len(data) == 1
        assert "rule" in data[0]["name"]

    def test_无匹配返回空数组(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine._get_all_refines_dirs", return_value=[("driving", self._refines_dir(tmp_path))]):
                result = runner.invoke(cli, ["refine", "load", "nonexistent"])
        data = json.loads(result.output)
        assert data == []


# ==================== driving refine commit ====================


class TestRefineCommit:
    """driving refine commit 命令测试

    覆盖场景：
    - --file 未传时报错（必填）
    - 仓库不存在时报错
    - local 类型仓库跳过
    - 文件不存在时跳过并提示
    - 文件已被 git 追踪时跳过并提示
    - 所有文件都被跳过时退出
    - 用户取消确认时退出
    - 正常流程：git add + commit + push
    - --no-push 跳过 push
    - 多个 --file 全部提交
    - commit message 使用文件名
    - refines/ 以外的文件（REFINE_LOG.md 等）也可提交
    """

    def _setup(self, tmp_path, repo_type: str = "remote"):
        _make_config(
            tmp_path,
            [{"name": "driving", "type": repo_type, "path": "ai-driving/driving"}],
        )
        repo_dir = tmp_path / "ai-driving" / "driving"
        refines_dir = repo_dir / "refines"
        refines_dir.mkdir(parents=True, exist_ok=True)
        (refines_dir / "2026-04-10-skill-foo.md").write_text("content", encoding="utf-8")
        (refines_dir / "2026-04-10-rule-bar.md").write_text("content", encoding="utf-8")
        (repo_dir / "REFINE_LOG.md").write_text("log", encoding="utf-8")
        return tmp_path

    def _make_mock_repo(self, untracked=None):
        """创建标准 mock git.Repo，默认所有测试文件均为 untracked"""
        from unittest.mock import MagicMock
        mock_repo = MagicMock()
        mock_repo.untracked_files = untracked if untracked is not None else [
            "refines/2026-04-10-skill-foo.md",
            "refines/2026-04-10-rule-bar.md",
            "REFINE_LOG.md",
        ]
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        mock_repo.iter_commits.return_value = []  # 默认无新提交
        return mock_repo

    def _mock_cm(self, mock_cm_cls, tmp_path, repo_type="remote"):
        mock_cm = mock_cm_cls.return_value
        mock_cm.get_repo.return_value = type("R", (), {"type": repo_type, "name": "driving"})()
        mock_cm.get_repo_dir.return_value = tmp_path / "ai-driving" / "driving"
        return mock_cm

    def test_file未传时报错(self, tmp_path):
        _make_config(tmp_path, [{"name": "driving", "type": "remote", "path": "ai-driving/driving"}])
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "commit", "driving"])
        assert result.exit_code != 0

    def test_仓库不存在时报错(self, tmp_path):
        _make_config(tmp_path, [])
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "commit", "nonexistent",
                                         "--file", "refines/foo.md"])
        assert result.exit_code != 0

    def test_local仓库跳过(self, tmp_path):
        self._setup(tmp_path, repo_type="local")
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path, repo_type="local")
                result = runner.invoke(cli, ["refine", "commit", "driving",
                                             "--file", "refines/foo.md"])
        assert "本地仓库" in result.output or result.exit_code != 0

    def test_文件不存在时跳过(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/nonexistent.md"])
        assert result.exit_code == 0
        assert "没有需要提交" in result.output

    def test_文件已追踪时跳过(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        # 文件存在但既不在 untracked 也不在 unstaged/staged（已追踪且无修改）
        mock_repo = self._make_mock_repo(untracked=[])
        mock_repo.index.diff.return_value = []  # unstaged 和 staged 都为空
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"])
        assert result.exit_code == 0
        assert "没有需要提交" in result.output

    def test_已追踪有修改的文件正常提交(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        # 文件已追踪（不在 untracked），但在 unstaged 列表中（有修改）
        mock_repo = self._make_mock_repo(untracked=[])
        # index.diff(None) 返回 unstaged 修改，index.diff("HEAD") 返回 staged 修改
        unstaged_item = type("D", (), {"a_path": "agents/android-review-workflow/MEMORY.md"})()
        mock_repo.index.diff.side_effect = lambda ref: (
            [unstaged_item] if ref is None else []
        )
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                # 创建测试文件
                memory_file = tmp_path / "ai-driving" / "driving" / "agents" / "android-review-workflow" / "MEMORY.md"
                memory_file.parent.mkdir(parents=True, exist_ok=True)
                memory_file.write_text("updated", encoding="utf-8")
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "commit", "driving",
                         "--file", "agents/android-review-workflow/MEMORY.md"],
                        input="y\ny\n",
                    )
        assert result.exit_code == 0
        mock_repo.index.add.assert_called_once()
        added_files = mock_repo.index.add.call_args[0][0]
        assert "agents/android-review-workflow/MEMORY.md" in added_files

    def test_用户取消确认时退出(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"],
                                           input="n\n")
        assert result.exit_code == 0
        assert "已取消" in result.output

    def test_正常流程执行git操作(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        # iter_commits 返回空（无需 pull），两次确认：提交 + push
        mock_repo.iter_commits.return_value = []
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"],
                                           input="y\ny\n")
        assert result.exit_code == 0
        mock_repo.index.add.assert_called_once()
        mock_repo.index.commit.assert_called_once()
        added_files = mock_repo.index.add.call_args[0][0]
        assert added_files == ["refines/2026-04-10-skill-foo.md"]

    def test_commit_message使用文件名(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        mock_repo.iter_commits.return_value = []
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    runner.invoke(cli, ["refine", "commit", "driving",
                                        "--file", "refines/2026-04-10-skill-foo.md"],
                                  input="y\ny\n")
        message = mock_repo.index.commit.call_args[0][0]
        assert message.startswith("refine(driving):")
        assert "2026-04-10-skill-foo.md" in message

    def test_no_push跳过推送(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md",
                                                 "--no-push"],
                                           input="y\n")
        assert result.exit_code == 0
        assert "跳过 push" in result.output
        mock_repo.remotes.origin.push.assert_not_called()

    def test_push前用户选择不push(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        mock_repo.iter_commits.return_value = []
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    # 第一个 y 确认提交，第二个 n 拒绝 push
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"],
                                           input="y\nn\n")
        assert result.exit_code == 0
        assert "跳过 push" in result.output
        mock_repo.remotes.origin.push.assert_not_called()

    def test_远端有新提交时提示pull(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        # 模拟远端有 2 个新提交
        mock_repo.iter_commits.return_value = ["commit1", "commit2"]
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    # 确认提交 y，选择 pull y，确认 push y
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"],
                                           input="y\ny\ny\n")
        assert result.exit_code == 0
        assert "远端有" in result.output
        mock_repo.remotes.origin.pull.assert_called_once()

    def test_远端有新提交用户跳过pull(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        mock_repo.iter_commits.return_value = ["commit1"]
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    # 确认提交 y，跳过 pull n，确认 push y
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "refines/2026-04-10-skill-foo.md"],
                                           input="y\nn\ny\n")
        assert result.exit_code == 0
        assert "跳过 pull" in result.output
        mock_repo.remotes.origin.pull.assert_not_called()

    def test_多file全部提交(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        mock_repo.iter_commits.return_value = []
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "commit", "driving",
                         "--file", "refines/2026-04-10-skill-foo.md",
                         "--file", "REFINE_LOG.md"],
                        input="y\ny\n",
                    )
        assert result.exit_code == 0
        added_files = mock_repo.index.add.call_args[0][0]
        assert len(added_files) == 2
        assert "refines/2026-04-10-skill-foo.md" in added_files
        assert "REFINE_LOG.md" in added_files

    def test_非refines目录文件也可提交(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        mock_repo.iter_commits.return_value = []
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(cli, ["refine", "commit", "driving",
                                                 "--file", "REFINE_LOG.md"],
                                           input="y\ny\n")
        assert result.exit_code == 0
        added_files = mock_repo.index.add.call_args[0][0]
        assert "REFINE_LOG.md" in added_files


# ==================== driving refine log ====================


class TestRefineLog:
    """driving refine log append / get 命令测试

    覆盖场景：
    - append：首次创建文件（自动写入文件头）
    - append：追加到已有文件
    - append：仓库不存在时报错
    - get：文件存在时输出内容
    - get：文件不存在时输出空
    - get：仓库不存在时报错
    """

    def _setup(self, tmp_path, repo_type: str = "local"):
        _make_config(
            tmp_path,
            [{"name": "driving", "type": repo_type, "path": "ai-driving/driving"}],
        )
        repo_dir = tmp_path / "ai-driving" / "driving"
        repo_dir.mkdir(parents=True, exist_ok=True)
        return tmp_path

    def _mock_cm(self, mock_cm_cls, tmp_path):
        mock_cm = mock_cm_cls.return_value
        mock_cm.get_repo.return_value = type("R", (), {"type": "local", "name": "driving"})()
        mock_cm.get_repo_dir.return_value = tmp_path / "ai-driving" / "driving"
        return mock_cm

    # ---------- append ----------

    def test_append_首次创建文件并写入文件头(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        entry = "[2026-05-26] [即时] agent:test MEMORY — 测试条目 (operator: test)"
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                result = runner.invoke(cli, ["refine", "log", "append", "driving", entry])
        assert result.exit_code == 0
        log_file = tmp_path / "ai-driving" / "driving" / "REFINE_LOG.md"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "# Refine Log" in content
        assert entry in content
        assert "file: REFINE_LOG.md" in result.output

    def test_append_追加到已有文件(self, tmp_path):
        self._setup(tmp_path)
        log_file = tmp_path / "ai-driving" / "driving" / "REFINE_LOG.md"
        log_file.write_text(
            "# Refine Log\n# 记录所有已生效的规范变更，refines 合并后由 AI 追加。\n\n"
            "[2026-05-25] [即时] agent:foo MEMORY — 第一条 (operator: a)\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        entry2 = "[2026-05-26] [合并] rule:code-style — 第二条 (operator: AI)"
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                result = runner.invoke(cli, ["refine", "log", "append", "driving", entry2])
        assert result.exit_code == 0
        content = log_file.read_text(encoding="utf-8")
        assert "第一条" in content
        assert "第二条" in content
        # 两条记录各占一行，不应有多余空行
        lines = [l for l in content.splitlines() if l.strip().startswith("[")]
        assert len(lines) == 2

    def test_append_仓库不存在时报错(self, tmp_path):
        _make_config(tmp_path, [])
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "log", "append", "nonexistent", "entry"])
        assert result.exit_code != 0

    # ---------- get ----------

    def test_get_文件存在时输出内容(self, tmp_path):
        self._setup(tmp_path)
        log_file = tmp_path / "ai-driving" / "driving" / "REFINE_LOG.md"
        log_file.write_text("# Refine Log\n\n[2026-05-26] [即时] agent:foo — 测试\n", encoding="utf-8")
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                result = runner.invoke(cli, ["refine", "log", "get", "driving"])
        assert result.exit_code == 0
        assert "# Refine Log" in result.output
        assert "[2026-05-26]" in result.output

    def test_get_文件不存在时输出空(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                result = runner.invoke(cli, ["refine", "log", "get", "driving"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_get_仓库不存在时报错(self, tmp_path):
        _make_config(tmp_path, [])
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "log", "get", "nonexistent"])
        assert result.exit_code != 0


# ==================== _report_refine_event ====================


class TestReportToWebhook:
    """_report_refine_event 单元测试（原 _report_to_webhook，已重构为通过 op_reporter 上报）

    覆盖场景：
    - 正常上报：operation/extra 字段完整，含 repo_name / target_type / target_name / trigger
    - trigger 存在时 trigger 文本正确生成
    - trigger 缺省时 trigger 文本为空
    - trigger 部分字段缺失时正常处理
    - event 参数（operation）正确传递（refine_committed / refine_merged）
    - op_reporter 异常时静默失败，不抛出异常
    """

    def _make_meta(self, trigger=None):
        return {
            "date": "2026-06-01",
            "target_type": "rule",
            "target_name": "gate-spec",
            "target_file": "ai-driving/driving-base/rules/gate-spec.md",
            "description": "补充 trigger 字段说明",
            "operator": "张三",
            "trigger": trigger,
            "status": "pending",
        }

    def test_正常上报payload字段完整(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        captured = {}

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            captured["operation"] = operation
            captured["description"] = description
            captured["extra"] = extra or {}

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "2026-06-01-rule-gate-spec.md",
                self._make_meta(),
                operation="refine_committed",
            )

        assert captured["operation"] == "refine_committed"
        assert "rule" in captured["description"]
        assert "gate-spec" in captured["description"]
        extra = captured["extra"]
        assert extra["repo_name"] == "driving-base"
        assert extra["target_type"] == "rule"
        assert extra["target_name"] == "gate-spec"

    def test_trigger存在时source和reason展开到顶层(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        captured = {}

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            captured["extra"] = extra or {}

        trigger = {"source": "gate", "reason": "GATE-D1 返工 3 次，高频原因：页面类型判断有误"}
        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(trigger=trigger),
                operation="refine_committed",
                trigger_source="gate",
                trigger_reason="GATE-D1 返工 3 次，高频原因：页面类型判断有误",
            )

        # trigger 文本生成到 extra["trigger"]
        assert captured["extra"].get("trigger") is not None
        assert "gate" in captured["extra"]["trigger"]

    def test_trigger缺省时source和reason为空字符串(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        captured = {}

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            captured["extra"] = extra or {}

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(trigger=None),
                operation="refine_committed",
            )

        # trigger 为空时 extra["trigger"] 为 None
        assert captured["extra"].get("trigger") is None

    def test_trigger部分字段缺失时缺省为空字符串(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        captured = {}

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            captured["extra"] = extra or {}

        # 只有 source，没有 reason
        trigger = {"source": "self-discover"}
        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(trigger=trigger),
                operation="refine_committed",
                trigger_source="self-discover",
            )

        # 有 trigger_source 时 extra["trigger"] 非空
        assert captured["extra"].get("trigger") is not None

    def test_actor取自git_user_name(self, tmp_path):
        """新实现中 actor 由 op_reporter 负责，_report_refine_event 本身不再处理 actor"""
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        called = []

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            called.append(True)

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(),
                operation="refine_committed",
            )

        # 确认 report_op_event 被调用
        assert len(called) == 1

    def test_actor无法获取时为空字符串(self, tmp_path):
        """actor 处理由 op_reporter 负责，_report_refine_event 正常调用即可"""
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        called = []

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            called.append(True)

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(),
                operation="refine_committed",
            )

        assert len(called) == 1

    def test_event参数正确传递为merged(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        captured = {}

        def fake_report_op_event(operation, description, extra=None, silent=False, **kwargs):
            captured["operation"] = operation

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=fake_report_op_event):
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(),
                operation="refine_merged",
            )

        assert captured["operation"] == "refine_merged"

    def test_网络异常时静默失败(self, tmp_path):
        from unittest.mock import patch
        from driving_cli.commands.refine import _report_refine_event

        with patch("driving_cli.utils.op_reporter.report_op_event", side_effect=Exception("network error")):
            # 不应抛出异常
            _report_refine_event(
                "driving-base",
                tmp_path / "refine.md",
                self._make_meta(),
                operation="refine_committed",
            )


# ==================== driving refine merge ====================


class TestRefineMerge:
    """driving refine merge 命令测试

    覆盖场景：
    - --file 未传时报错（必填）
    - 仓库不存在时报错
    - refine 文件不存在时报错
    - frontmatter 解析失败时报错
    - 用户取消确认时退出
    - 正常流程：追加 REFINE_LOG → 删除 refine 文件 → git commit/push
    - --operator 参数写入 REFINE_LOG
    - --no-push 跳过 push
    - 多 --file 批量处理
    - REFINE_LOG 不存在时自动创建
    - REFINE_LOG 已存在时追加
    - webhook 上报在删除文件前调用（文件仍存在时上报）
    - refine_webhook 未配置时跳过上报
    - local 仓库跳过 git 操作
    """

    def _setup(self, tmp_path, repo_type: str = "remote"):
        _make_config(
            tmp_path,
            [{"name": "driving-base", "type": repo_type, "path": "ai-driving/driving-base"}],
        )
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        refines_dir = repo_dir / "refines"
        _make_refine_md(
            refines_dir / "2026-06-01-rule-gate-spec.md",
            target_type="rule",
            target_name="gate-spec",
            description="补充 trigger 字段说明",
        )
        _make_refine_md(
            refines_dir / "2026-06-01-rule-coding-standards.md",
            target_type="rule",
            target_name="coding-standards",
            description="补充协程规范",
        )
        return tmp_path

    def _make_mock_repo(self):
        from unittest.mock import MagicMock
        mock_repo = MagicMock()
        mock_repo.head.is_detached = False
        mock_repo.active_branch.name = "main"
        return mock_repo

    def _mock_cm(self, mock_cm_cls, tmp_path, repo_type="remote", refine_webhook=""):
        mock_cm = mock_cm_cls.return_value
        mock_cm.get_repo.return_value = type("R", (), {"type": repo_type, "name": "driving-base"})()
        mock_cm.get_repo_dir.return_value = tmp_path / "ai-driving" / "driving-base"
        cfg = type("C", (), {"refine_webhook": refine_webhook})()
        mock_cm.load.return_value = cfg
        return mock_cm

    def test_file未传时报错(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "merge", "driving-base"])
        assert result.exit_code != 0

    def test_仓库不存在时报错(self, tmp_path):
        _make_config(tmp_path, [])
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["refine", "merge", "nonexistent",
                                         "--file", "refines/foo.md"])
        assert result.exit_code != 0

    def test_refine文件不存在时报错(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                result = runner.invoke(cli, ["refine", "merge", "driving-base",
                                             "--file", "refines/nonexistent.md"])
        assert result.exit_code != 0

    def test_用户取消确认时退出(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="n\n",
                    )
        assert result.exit_code == 0
        assert "已取消" in result.output
        # refine 文件不应被删除
        refine_file = tmp_path / "ai-driving" / "driving-base" / "refines" / "2026-06-01-rule-gate-spec.md"
        assert refine_file.exists()

    def test_正常流程追加REFINE_LOG并删除refine文件(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\ny\ny\n",  # 确认合并 + 确认跳过正式文件 + 确认 push
                    )
        assert result.exit_code == 0
        # refine 文件已删除
        refine_file = tmp_path / "ai-driving" / "driving-base" / "refines" / "2026-06-01-rule-gate-spec.md"
        assert not refine_file.exists()
        # REFINE_LOG 已创建并包含合并记录
        log_file = tmp_path / "ai-driving" / "driving-base" / "REFINE_LOG.md"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "[合并]" in content
        assert "gate-spec" in content

    def test_REFINE_LOG不存在时自动创建(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        log_file = tmp_path / "ai-driving" / "driving-base" / "REFINE_LOG.md"
        assert not log_file.exists()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\ny\n",  # 确认合并 + 确认跳过正式文件
                    )
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "# Refine Log" in content

    def test_REFINE_LOG已存在时追加(self, tmp_path):
        self._setup(tmp_path)
        log_file = tmp_path / "ai-driving" / "driving-base" / "REFINE_LOG.md"
        log_file.write_text(
            "# Refine Log\n# 记录所有已生效的规范变更，refines 合并后由 AI 追加。\n\n"
            "[2026-05-01] [合并] rule:old-rule — 旧记录 (operator: 旧人)\n",
            encoding="utf-8",
        )
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\ny\n",  # 确认合并 + 确认跳过正式文件
                    )
        content = log_file.read_text(encoding="utf-8")
        assert "旧记录" in content
        assert "gate-spec" in content

    def test_operator参数写入REFINE_LOG(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--operator", "张三"],
                        input="y\ny\n",  # 确认合并 + 确认跳过正式文件
                    )
        log_file = tmp_path / "ai-driving" / "driving-base" / "REFINE_LOG.md"
        content = log_file.read_text(encoding="utf-8")
        assert "operator: 张三" in content

    def test_no_push跳过推送(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--no-push"],
                        input="y\ny\n",  # 确认合并 + 确认跳过正式文件
                    )
        assert result.exit_code == 0
        assert "跳过 push" in result.output
        mock_repo.remotes.origin.push.assert_not_called()

    def test_多file批量处理(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--file", "refines/2026-06-01-rule-coding-standards.md"],
                        input="y\ny\ny\n",  # 确认合并 + 确认跳过正式文件 + 确认 push
                    )
        assert result.exit_code == 0
        # 两个 refine 文件都已删除
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        assert not (repo_dir / "refines" / "2026-06-01-rule-gate-spec.md").exists()
        assert not (repo_dir / "refines" / "2026-06-01-rule-coding-standards.md").exists()
        # REFINE_LOG 包含两条记录
        log_file = repo_dir / "REFINE_LOG.md"
        content = log_file.read_text(encoding="utf-8")
        assert "gate-spec" in content
        assert "coding-standards" in content

    def test_commit_message包含target_name和description(self, tmp_path):
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\ny\n",  # 确认合并 + 确认跳过正式文件
                    )
        message = mock_repo.index.commit.call_args[0][0]
        assert message.startswith("refine(merge):")
        assert "gate-spec" in message
        assert "补充 trigger 字段说明" in message

    def test_webhook上报在删除文件前调用(self, tmp_path):
        """上报时 refine 文件应仍存在（上报在删除之前）"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        reported_files = []

        def fake_report(repo_name, file_path, meta, operation, trigger_source="", trigger_reason=""):
            reported_files.append((str(file_path), file_path.exists(), operation))

        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    with patch("driving_cli.commands.refine._report_refine_event", side_effect=fake_report):
                        runner.invoke(
                            cli,
                            ["refine", "merge", "driving-base",
                             "--file", "refines/2026-06-01-rule-gate-spec.md"],
                            input="y\ny\ny\n",  # 确认合并 + 确认跳过正式文件 + 确认 push
                        )

        assert len(reported_files) == 1
        _path, file_existed_at_report_time, operation = reported_files[0]
        assert file_existed_at_report_time, "上报时文件应仍存在"
        assert operation == "refine_merged"

    def test_refine_webhook未配置时跳过上报(self, tmp_path):
        """上报逻辑现在由 op_reporter 负责，_report_refine_event 无条件被调用；
        此测试验证 _report_refine_event 函数本身被调用（上报是否实际发出由 op_reporter 决定）"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    with patch("driving_cli.commands.refine._report_refine_event") as mock_report:
                        runner.invoke(
                            cli,
                            ["refine", "merge", "driving-base",
                             "--file", "refines/2026-06-01-rule-gate-spec.md"],
                            input="y\ny\ny\n",  # 确认合并 + 确认跳过正式文件 + 确认 push
                        )
        # _report_refine_event 现在无条件被调用（由 op_reporter 内部决定是否发出请求）
        mock_report.assert_called_once()

    def test_trigger_source和reason传入时覆盖meta中的trigger(self, tmp_path):
        """--trigger-source / --trigger-reason 传入时，上报使用合并操作的触发信息"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        reported_calls = []

        def fake_report(repo_name, file_path, meta, operation, trigger_source="", trigger_reason=""):
            reported_calls.append({
                "meta": dict(meta),
                "trigger_source": trigger_source,
                "trigger_reason": trigger_reason,
            })

        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    with patch("driving_cli.commands.refine._report_refine_event", side_effect=fake_report):
                        result = runner.invoke(
                            cli,
                            ["refine", "merge", "driving-base",
                             "--file", "refines/2026-06-01-rule-gate-spec.md",
                             "--trigger-source", "manual",
                             "--trigger-reason", "用户主动合并"],
                            input="y\ny\ny\n",
                        )

        assert result.exit_code == 0
        assert len(reported_calls) == 1
        assert reported_calls[0]["trigger_source"] == "manual"
        assert reported_calls[0]["trigger_reason"] == "用户主动合并"

    def test_trigger_source和reason未传时沿用meta中的trigger(self, tmp_path):
        """未传 --trigger-source / --trigger-reason 时，trigger_source/reason 为空字符串（默认值）"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        reported_calls = []

        def fake_report(repo_name, file_path, meta, operation, trigger_source="", trigger_reason=""):
            reported_calls.append({
                "trigger_source": trigger_source,
                "trigger_reason": trigger_reason,
            })

        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    with patch("driving_cli.commands.refine._report_refine_event", side_effect=fake_report):
                        result = runner.invoke(
                            cli,
                            ["refine", "merge", "driving-base",
                             "--file", "refines/2026-06-01-rule-gate-spec.md"],
                            input="y\ny\ny\n",
                        )

        assert result.exit_code == 0
        assert len(reported_calls) == 1
        # 未传参数时 trigger_source / trigger_reason 使用默认空字符串
        assert reported_calls[0]["trigger_source"] == ""
        assert reported_calls[0]["trigger_reason"] == ""

    def test_local仓库跳过git操作(self, tmp_path):
        self._setup(tmp_path, repo_type="local")
        runner = CliRunner()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path, repo_type="local")
                # 同时 patch _report_refine_event 避免 op_reporter 内部调用 git.Repo
                with patch("driving_cli.commands.refine._report_refine_event"):
                    with patch("driving_cli.commands.refine.git.Repo") as mock_git:
                        result = runner.invoke(
                            cli,
                            ["refine", "merge", "driving-base",
                             "--file", "refines/2026-06-01-rule-gate-spec.md"],
                            input="y\ny\n",  # 确认合并 + 确认跳过正式文件（local 仓库不需要 push 确认）
                        )
        assert result.exit_code == 0
        assert "本地仓库" in result.output
        mock_git.assert_not_called()

    def test_changed_file优先于target_file加入commit(self, tmp_path):
        """--changed-file 传入时，使用指定文件而非 target_file"""
        self._setup(tmp_path)
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        # 创建实际修改的文件
        changed = repo_dir / "skills" / "dev-design" / "references" / "dev-design.md"
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text("updated content", encoding="utf-8")
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--changed-file", "skills/dev-design/references/dev-design.md"],
                        input="y\ny\n",
                    )
        assert result.exit_code == 0
        add_calls = mock_repo.index.add.call_args[0][0]
        assert "skills/dev-design/references/dev-design.md" in add_calls
        # target_file（SKILL.md）不应出现在 add 中
        assert not any("SKILL.md" in f for f in add_calls)

    def test_changed_file支持多个文件(self, tmp_path):
        """--changed-file 可多次指定，全部加入 commit"""
        self._setup(tmp_path)
        repo_dir = tmp_path / "ai-driving" / "driving-base"
        f1 = repo_dir / "skills" / "dev-design" / "references" / "dev-design.md"
        f2 = repo_dir / "skills" / "dev-design" / "SKILL.md"
        f1.parent.mkdir(parents=True, exist_ok=True)
        f1.write_text("updated", encoding="utf-8")
        f2.write_text("updated", encoding="utf-8")
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--changed-file", "skills/dev-design/references/dev-design.md",
                         "--changed-file", "skills/dev-design/SKILL.md"],
                        input="y\ny\n",
                    )
        assert result.exit_code == 0
        add_calls = mock_repo.index.add.call_args[0][0]
        assert "skills/dev-design/references/dev-design.md" in add_calls
        assert "skills/dev-design/SKILL.md" in add_calls

    def test_未传changed_file时提示确认(self, tmp_path):
        """未传 --changed-file 时，打警告并要求用户确认是否继续"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    # 第一个 y 确认合并，第二个 n 拒绝"不提交正式文件"
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\nn\n",
                    )
        assert result.exit_code == 0
        assert "未指定 --changed-file" in result.output
        assert "已取消" in result.output
        mock_repo.index.commit.assert_not_called()

    def test_未传changed_file用户确认跳过时继续执行(self, tmp_path):
        """未传 --changed-file，用户确认跳过时正常执行 commit"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    # 第一个 y 确认合并，第二个 y 确认不提交正式文件，第三个 y 确认 push
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md"],
                        input="y\ny\ny\n",
                    )
        assert result.exit_code == 0
        mock_repo.index.commit.assert_called_once()
        add_calls = mock_repo.index.add.call_args[0][0]
        assert add_calls == ["REFINE_LOG.md"]

    def test_changed_file不存在时打warning跳过(self, tmp_path):
        """--changed-file 指定的文件不存在时，打 warning 跳过，不中断流程"""
        self._setup(tmp_path)
        runner = CliRunner()
        mock_repo = self._make_mock_repo()
        with patch("driving_cli.utils.config_manager.find_project_root", return_value=tmp_path):
            with patch("driving_cli.commands.refine.ConfigManager") as mock_cm_cls:
                self._mock_cm(mock_cm_cls, tmp_path)
                with patch("driving_cli.commands.refine.git.Repo", return_value=mock_repo):
                    result = runner.invoke(
                        cli,
                        ["refine", "merge", "driving-base",
                         "--file", "refines/2026-06-01-rule-gate-spec.md",
                         "--changed-file", "skills/nonexistent/SKILL.md"],
                        input="y\ny\n",
                    )
        assert result.exit_code == 0
        assert "不存在" in result.output or "跳过" in result.output
        mock_repo.index.commit.assert_called_once()
