"""gate 子命令组单元测试和属性测试

变更说明（相对于初版）：
- gate list 默认改为 Rich 表格输出，--json 保持不变
- gate load 参数改为可选多值（nargs=-1），不传时加载全部
- gate load 输出格式统一为 {"system_prompt": "...", "gates": [...]}
  - system_prompt 来自 gates.json 顶层，多仓库拼接，为空时不输出
  - 任一 ID 找不到时 gates 返回空数组，不退出
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from driving_cli.cli import cli
from driving_cli.commands.gate import load_gates_from_manifest


# ==================== Helpers ====================


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


def _make_manifest(repo_dir: Path, gates_path: str = "rules/gates.json", extra: dict = None) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    data = {"min_cli_version": "1.0.0"}
    if gates_path is not None:
        data["gates"] = gates_path
    if extra:
        data.update(extra)
    (repo_dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


def _make_gates_json(
    repo_dir: Path,
    gates: list,
    rel_path: str = "rules/gates.json",
    system_prompt: str = "",
) -> None:
    gates_file = repo_dir / rel_path
    gates_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": "1.0.0", "description": "test gates", "gates": gates}
    if system_prompt:
        data["system_prompt"] = system_prompt
    gates_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _sample_gate(gate_id: str = "GATE-R1", template_style: str = "template") -> dict:
    gate = {
        "id": gate_id,
        "name": f"Gate {gate_id}",
        "type": "mandatory",
        "location": "some-skill -> step.md",
        "trigger": "触发条件",
        "actions": {"确认": "继续", "取消": "停止"},
    }
    if template_style == "template":
        gate["template"] = ["line1", "line2"]
    else:
        gate["templates"] = {"A_variant": ["line1"], "B_variant": ["line2"]}
    return gate


def _parse_load_output(output: str) -> dict:
    """从 gate load 输出中提取 JSON（跳过前面可能的 WARNING 行）。"""
    idx = output.index("{")
    return json.loads(output[idx:])


# ==================== load_gates_from_manifest ====================


class TestLoadGatesFromManifest:
    def test_manifest不存在时返回None(self, tmp_path):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        assert load_gates_from_manifest("repo", repo_dir) is None

    def test_manifest无gates字段时返回None(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir, gates_path=None)
        assert load_gates_from_manifest("repo", repo_dir) is None

    def test_gates文件不存在时返回None(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        assert load_gates_from_manifest("repo", repo_dir) is None

    def test_gates_json格式非法时返回None(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        f = repo_dir / "rules" / "gates.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{ invalid json }", encoding="utf-8")
        assert load_gates_from_manifest("repo", repo_dir) is None

    def test_gates字段不是数组时返回None(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        f = repo_dir / "rules" / "gates.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"version": "1.0", "gates": {"not": "array"}}), encoding="utf-8")
        assert load_gates_from_manifest("repo", repo_dir) is None

    def test_正常解析返回gate列表(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        _make_gates_json(repo_dir, [_sample_gate("GATE-R1"), _sample_gate("GATE-D1")])
        result = load_gates_from_manifest("repo", repo_dir)
        assert result is not None
        assert len(result) == 2
        assert result[0]["id"] == "GATE-R1"

    def test_所有字段原样保留(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        gate = _sample_gate("GATE-R1", template_style="template")
        _make_gates_json(repo_dir, [gate])
        result = load_gates_from_manifest("repo", repo_dir)
        assert result[0]["template"] == gate["template"]
        assert result[0]["actions"] == gate["actions"]

    def test_templates格式也能正确解析(self, tmp_path):
        repo_dir = tmp_path / "repo"
        _make_manifest(repo_dir)
        gate = _sample_gate("GATE-R5", template_style="templates")
        _make_gates_json(repo_dir, [gate])
        result = load_gates_from_manifest("repo", repo_dir)
        assert "templates" in result[0]
        assert result[0]["templates"] == gate["templates"]


# ==================== gate list 命令 ====================


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_with_gates(tmp_path):
    _make_config(tmp_path, [
        {"name": "driving", "type": "local", "path": "ai-driving/driving", "local_path": None},
    ])
    repo_dir = tmp_path / "ai-driving" / "driving"
    _make_manifest(repo_dir)
    _make_gates_json(repo_dir, [_sample_gate("GATE-R1"), _sample_gate("GATE-D1")])
    return tmp_path


@pytest.fixture
def project_multi_repo(tmp_path):
    _make_config(tmp_path, [
        {"name": "repo-a", "type": "local", "path": "ai-driving/repo-a", "local_path": None},
        {"name": "repo-b", "type": "local", "path": "ai-driving/repo-b", "local_path": None},
    ])
    repo_a = tmp_path / "ai-driving" / "repo-a"
    repo_b = tmp_path / "ai-driving" / "repo-b"
    _make_manifest(repo_a)
    _make_manifest(repo_b)
    _make_gates_json(repo_a, [_sample_gate("GATE-A1")])
    _make_gates_json(repo_b, [_sample_gate("GATE-B1")])
    return tmp_path


class TestGateListCommand:
    def test_无仓库配置时输出提示(self, runner, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "未找到任何 gate 配置" in result.output

    def test_无gates字段时输出提示(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
        ])
        _make_manifest(tmp_path / "ai-driving" / "repo", gates_path=None)
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "未找到任何 gate 配置" in result.output

    def test_表格模式包含gate_id(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "GATE-R1" in result.output
        assert "GATE-D1" in result.output

    def test_表格模式包含仓库名(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "driving" in result.output

    def test_表格模式包含type和location(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "mandatory" in result.output
        assert "some-skill" in result.output

    def test_多仓库均出现在表格中(self, runner, project_multi_repo):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_multi_repo):
            result = runner.invoke(cli, ["gate", "list"])
        assert result.exit_code == 0
        assert "repo-a" in result.output
        assert "repo-b" in result.output
        assert "GATE-A1" in result.output
        assert "GATE-B1" in result.output


class TestGateListJsonCommand:
    def test_json模式输出合法JSON数组(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_json模式每条记录包含五个必需字段(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for item in data:
            for field in ("id", "name", "type", "location", "repo"):
                assert field in item

    def test_json模式repo字段正确(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "list", "--json"])
        assert result.exit_code == 0
        for item in json.loads(result.output):
            assert item["repo"] == "driving"

    def test_json模式无gate时输出提示(self, runner, tmp_path):
        _make_config(tmp_path, [])
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "list", "--json"])
        assert result.exit_code == 0
        assert "未找到任何 gate 配置" in result.output


# ==================== gate load 命令（新接口）====================


class TestGateLoadCommand:
    # ── 不传 ID：加载全部 ──────────────────────────────────────

    def test_不传id时加载全部gate(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "gates" in data
        assert len(data["gates"]) == 2

    def test_不传id时输出为对象格式(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "gates" in data

    def test_不传id时无system_prompt字段则不输出(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "system_prompt" not in data

    def test_有system_prompt时输出该字段(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
        ])
        repo_dir = tmp_path / "ai-driving" / "repo"
        _make_manifest(repo_dir)
        _make_gates_json(repo_dir, [_sample_gate("GATE-R1")], system_prompt="你是门禁助手")
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["system_prompt"] == "你是门禁助手"

    def test_多仓库system_prompt拼接(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo-a", "type": "local", "path": "ai-driving/repo-a", "local_path": None},
            {"name": "repo-b", "type": "local", "path": "ai-driving/repo-b", "local_path": None},
        ])
        repo_a = tmp_path / "ai-driving" / "repo-a"
        repo_b = tmp_path / "ai-driving" / "repo-b"
        _make_manifest(repo_a)
        _make_manifest(repo_b)
        _make_gates_json(repo_a, [_sample_gate("GATE-A1")], system_prompt="提示A")
        _make_gates_json(repo_b, [_sample_gate("GATE-B1")], system_prompt="提示B")
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "load"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "提示A" in data["system_prompt"]
        assert "提示B" in data["system_prompt"]

    # ── 传单个 ID ──────────────────────────────────────────────

    def test_单id找到时gates包含该gate(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-R1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["gates"]) == 1
        assert data["gates"][0]["id"] == "GATE-R1"

    def test_单id找到时gate包含所有原始字段(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-R1"])
        assert result.exit_code == 0
        gate = json.loads(result.output)["gates"][0]
        for field in ("id", "name", "type", "location", "trigger", "actions"):
            assert field in gate
        assert "template" in gate or "templates" in gate

    def test_单id不存在时gates为空数组(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-NONEXISTENT"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["gates"] == []

    def test_大小写不敏感_小写匹配(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "gate-r1"])
        assert result.exit_code == 0
        assert json.loads(result.output)["gates"][0]["id"] == "GATE-R1"

    def test_大小写不敏感_混合大小写匹配(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "Gate-R1"])
        assert result.exit_code == 0
        assert json.loads(result.output)["gates"][0]["id"] == "GATE-R1"

    # ── 传多个 ID ──────────────────────────────────────────────

    def test_多id全部找到时返回所有gate(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-R1", "GATE-D1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["gates"]) == 2
        ids = {g["id"] for g in data["gates"]}
        assert ids == {"GATE-R1", "GATE-D1"}

    def test_多id任一不存在时gates为空数组(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-R1", "GATE-MISSING"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["gates"] == []

    def test_多id结果按传入顺序排列(self, runner, project_with_gates):
        with patch("driving_cli.commands.gate.find_project_root", return_value=project_with_gates):
            result = runner.invoke(cli, ["gate", "load", "GATE-D1", "GATE-R1"])
        assert result.exit_code == 0
        gates = json.loads(result.output)["gates"]
        assert gates[0]["id"] == "GATE-D1"
        assert gates[1]["id"] == "GATE-R1"

    # ── 重复 ID ────────────────────────────────────────────────

    def test_重复ID返回第一个仓库结果(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo-first", "type": "local", "path": "ai-driving/repo-first", "local_path": None},
            {"name": "repo-second", "type": "local", "path": "ai-driving/repo-second", "local_path": None},
        ])
        repo_first = tmp_path / "ai-driving" / "repo-first"
        repo_second = tmp_path / "ai-driving" / "repo-second"
        _make_manifest(repo_first)
        _make_manifest(repo_second)
        _make_gates_json(repo_first, [{"id": "GATE-DUP", "name": "First Gate",
                                       "type": "mandatory", "location": "loc",
                                       "trigger": "t", "template": ["first"]}])
        _make_gates_json(repo_second, [{"id": "GATE-DUP", "name": "Second Gate",
                                        "type": "optional", "location": "loc",
                                        "trigger": "t", "template": ["second"]}])
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "load", "GATE-DUP"])
        assert result.exit_code == 0
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert data["gates"][0]["name"] == "First Gate"

    # ── 模板格式 ───────────────────────────────────────────────

    def test_template数组格式完整保留(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
        ])
        repo_dir = tmp_path / "ai-driving" / "repo"
        _make_manifest(repo_dir)
        gate = _sample_gate("GATE-T1", template_style="template")
        _make_gates_json(repo_dir, [gate])
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "load", "GATE-T1"])
        assert result.exit_code == 0
        g = json.loads(result.output)["gates"][0]
        assert g["template"] == gate["template"]

    def test_templates对象格式完整保留(self, runner, tmp_path):
        _make_config(tmp_path, [
            {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
        ])
        repo_dir = tmp_path / "ai-driving" / "repo"
        _make_manifest(repo_dir)
        gate = _sample_gate("GATE-T2", template_style="templates")
        _make_gates_json(repo_dir, [gate])
        with patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
            result = runner.invoke(cli, ["gate", "load", "GATE-T2"])
        assert result.exit_code == 0
        g = json.loads(result.output)["gates"][0]
        assert g["templates"] == gate["templates"]

    def test_gate_group已挂载到cli(self, runner):
        result = runner.invoke(cli, ["gate", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "load" in result.output


# ==================== 属性测试 ====================

from hypothesis import given, settings
from hypothesis import strategies as st

_gate_id_st = st.from_regex(r"GATE-[A-Z][0-9]{1,2}", fullmatch=True)
_repo_name_st = st.from_regex(r"[a-z][a-z0-9-]{0,9}", fullmatch=True)
_text_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _-",
    min_size=1,
    max_size=30,
)

_gate_template_st = st.fixed_dictionaries({
    "id": _gate_id_st,
    "name": _text_st,
    "type": st.sampled_from(["mandatory", "optional"]),
    "location": _text_st,
    "trigger": _text_st,
    "template": st.lists(st.text(min_size=0, max_size=20), min_size=0, max_size=3),
    "actions": st.dictionaries(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
        st.text(min_size=0, max_size=20),
        min_size=0,
        max_size=3,
    ),
})

_gate_templates_st = st.fixed_dictionaries({
    "id": _gate_id_st,
    "name": _text_st,
    "type": st.sampled_from(["mandatory", "optional"]),
    "location": _text_st,
    "trigger": _text_st,
    "templates": st.dictionaries(
        st.from_regex(r"[A-Z]_[a-z]{1,5}", fullmatch=True),
        st.lists(st.text(min_size=0, max_size=20), min_size=0, max_size=3),
        min_size=1,
        max_size=3,
    ),
    "actions": st.dictionaries(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=5),
        st.text(min_size=0, max_size=20),
        min_size=0,
        max_size=3,
    ),
})

_gate_any_st = st.one_of(_gate_template_st, _gate_templates_st)


# Feature: driving-gate-command, Property 3 & 4: gate list 输出字段完整性
@settings(max_examples=100)
@given(
    repo_name=_repo_name_st,
    gates=st.lists(_gate_any_st, min_size=1, max_size=5),
)
def test_property3_4_gate_list输出字段完整性(tmp_path_factory, repo_name, gates):
    """Property 3 & 4: gate list 输出字段完整性

    - 表格模式：每条 gate 的 id、name 内容都出现在输出中
    - --json 模式：每条记录包含 id、name、type、location、repo 五个字段

    **Validates: Requirements 2.2, 2.6**
    """
    import json as _json
    from unittest.mock import patch as _patch
    from click.testing import CliRunner as _Runner
    from driving_cli.cli import cli as _cli

    tmp_path = tmp_path_factory.mktemp("prop34")
    _make_config(tmp_path, [
        {"name": repo_name, "type": "local", "path": f"ai-driving/{repo_name}", "local_path": None},
    ])
    repo_dir = tmp_path / "ai-driving" / repo_name
    _make_manifest(repo_dir)
    _make_gates_json(repo_dir, gates)

    runner = _Runner()

    # Property 3: 表格模式字段完整性（只验证 id，name 可能被 Rich 截断）
    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        result = runner.invoke(_cli, ["gate", "list"])
    assert result.exit_code == 0
    for gate in gates:
        assert gate["id"] in result.output

    # Property 4: --json 模式字段完整性（验证 id、name 等所有字段完整输出）
    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        result_json = runner.invoke(_cli, ["gate", "list", "--json"])
    assert result_json.exit_code == 0
    data = _json.loads(result_json.output)
    assert isinstance(data, list)
    assert len(data) == len(gates)
    for item, gate in zip(data, gates):
        for field in ("id", "name", "type", "location", "repo"):
            assert field in item
        assert item["repo"] == repo_name
        assert item["name"] == gate["name"]


# Feature: driving-gate-command, Property 5 & 8 & 9: round-trip 属性
@settings(max_examples=100)
@given(gate=_gate_any_st)
def test_property5_8_9_round_trip(tmp_path_factory, gate):
    """Property 5 & 8 & 9: gates.json 解析 round-trip（含两种模板格式）

    gate load 输出的 gates[0] 再解析后，所有字段原样保留。

    **Validates: Requirements 3.2, 4.2, 4.3, 4.5**
    """
    import json as _json
    from unittest.mock import patch as _patch
    from click.testing import CliRunner as _Runner
    from driving_cli.cli import cli as _cli

    tmp_path = tmp_path_factory.mktemp("prop589")
    _make_config(tmp_path, [
        {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
    ])
    repo_dir = tmp_path / "ai-driving" / "repo"
    _make_manifest(repo_dir)
    _make_gates_json(repo_dir, [gate])

    runner = _Runner()
    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        result = runner.invoke(_cli, ["gate", "load", gate["id"]])
    assert result.exit_code == 0
    reparsed = _json.loads(result.output)["gates"][0]

    for key, value in gate.items():
        assert key in reparsed, f"字段 '{key}' 在 round-trip 后丢失"
        assert reparsed[key] == value, f"字段 '{key}' 值在 round-trip 后改变"


# Feature: driving-gate-command, Property 6: 大小写不敏感匹配
@settings(max_examples=100)
@given(gate=_gate_template_st)
def test_property6_大小写不敏感匹配(tmp_path_factory, gate):
    """Property 6: 大小写不敏感匹配

    gate-id 的大写、小写、混合大小写变体都应匹配到同一个 gate。

    **Validates: Requirements 3.5**
    """
    import json as _json
    from unittest.mock import patch as _patch
    from click.testing import CliRunner as _Runner
    from driving_cli.cli import cli as _cli

    tmp_path = tmp_path_factory.mktemp("prop6")
    _make_config(tmp_path, [
        {"name": "repo", "type": "local", "path": "ai-driving/repo", "local_path": None},
    ])
    repo_dir = tmp_path / "ai-driving" / "repo"
    _make_manifest(repo_dir)
    _make_gates_json(repo_dir, [gate])

    gate_id = gate["id"]
    runner = _Runner()

    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        r_upper = runner.invoke(_cli, ["gate", "load", gate_id.upper()])
    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        r_lower = runner.invoke(_cli, ["gate", "load", gate_id.lower()])

    assert r_upper.exit_code == 0
    assert r_lower.exit_code == 0
    id_upper = _json.loads(r_upper.output)["gates"][0]["id"]
    id_lower = _json.loads(r_lower.output)["gates"][0]["id"]
    assert id_upper == id_lower == gate_id


# Feature: driving-gate-command, Property 7: 重复 ID 返回第一个仓库
@settings(max_examples=100)
@given(
    gate=_gate_template_st,
    extra_repos=st.lists(
        st.from_regex(r"repo-[a-z]{2,4}", fullmatch=True),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
def test_property7_重复ID返回第一个仓库(tmp_path_factory, gate, extra_repos):
    """Property 7: 重复 ID 返回第一个仓库

    多仓库存在相同 gate-id 时，gate load 返回 driving.config.json 中排在最前面的仓库的 gate。

    **Validates: Requirements 3.4**
    """
    import json as _json
    from unittest.mock import patch as _patch
    from click.testing import CliRunner as _Runner
    from driving_cli.cli import cli as _cli

    tmp_path = tmp_path_factory.mktemp("prop7")
    first_repo = "repo-first"
    all_repos = [first_repo] + extra_repos

    _make_config(tmp_path, [
        {"name": r, "type": "local", "path": f"ai-driving/{r}", "local_path": None}
        for r in all_repos
    ])

    first_gate = dict(gate)
    first_gate["name"] = "FIRST_REPO_GATE"

    for repo_name in all_repos:
        repo_dir = tmp_path / "ai-driving" / repo_name
        _make_manifest(repo_dir)
        g = first_gate if repo_name == first_repo else dict(gate, name=f"OTHER_{repo_name}")
        _make_gates_json(repo_dir, [g])

    runner = _Runner()
    with _patch("driving_cli.commands.gate.find_project_root", return_value=tmp_path):
        result = runner.invoke(_cli, ["gate", "load", gate["id"]])

    assert result.exit_code == 0
    json_start = result.output.index("{")
    data = _json.loads(result.output[json_start:])
    assert data["gates"][0]["name"] == "FIRST_REPO_GATE"


# ==================== --platform 参数测试 ====================


def _make_blocking_gate(gate_id: str = "GATE-R5") -> dict:
    """创建一个 blocking 门禁（human_only auto_pass，始终需要交互）"""
    return {
        "id": gate_id,
        "name": f"Gate {gate_id}",
        "level": "blocking",
        "requires": [],
        "location": "test",
        "trigger": "测试触发",
        "template": ["请确认"],
        "actions": {
            "确认": {"next": "继续", "requires_note": False},
            "修改": {"next": "重新触发", "requires_note": True},
        },
        "auto_pass": {
            "mode": "full_auto",
            "conditions": [],
            "on_pass": {"action": "确认", "next": "自动通过"},
        },
    }


@pytest.fixture
def project_with_auto_pass_gate(tmp_path):
    """提供一个 full_auto 门禁（conditions 为空，始终自动通过）的测试项目"""
    _make_config(tmp_path, [
        {"name": "driving", "type": "local", "path": "ai-driving/driving", "local_path": None},
    ])
    repo_dir = tmp_path / "ai-driving" / "driving"
    _make_manifest(repo_dir)
    _make_gates_json(repo_dir, [_make_blocking_gate("GATE-R5")])
    return tmp_path


class TestGateRequestPlatformOption:
    """gate request --platform 参数测试"""

    def test_不传platform时state写入docs下(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
            ])
        assert result.exit_code == 0
        state_file = feature_dir / "docs" / "gate-state.json"
        assert state_file.exists()

    def test_传platform_android时state写入docs_android下(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "android",
            ])
        assert result.exit_code == 0
        state_file = feature_dir / "docs" / "android" / "gate-state.json"
        assert state_file.exists()

    def test_传platform_iOS时state写入docs_iOS下(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "iOS",
            ])
        assert result.exit_code == 0
        state_file = feature_dir / "docs" / "iOS" / "gate-state.json"
        assert state_file.exists()

    def test_传platform时默认路径无state文件(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "android",
            ])
        default_state_file = feature_dir / "docs" / "gate-state.json"
        assert not default_state_file.exists()


class TestGatePassPlatformOption:
    """gate pass --platform 参数测试"""

    def test_传platform时state写入正确路径(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "pass", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "harmony",
            ])
        assert result.exit_code == 0
        state_file = feature_dir / "docs" / "harmony" / "gate-state.json"
        assert state_file.exists()

    def test_不传platform时state写入docs下(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "pass", "GATE-R5",
                "--path", str(feature_dir),
            ])
        assert result.exit_code == 0
        state_file = feature_dir / "docs" / "gate-state.json"
        assert state_file.exists()


class TestGateStatusPlatformOption:
    """gate status --platform 参数测试"""

    def test_传platform时读取正确路径的状态(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        # 先写入 android 平台状态
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "android",
            ])
        # 再读取 android 平台状态
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "status",
                "--path", str(feature_dir),
                "--platform", "android",
            ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "GATE-R5" in data

    def test_无platform时读取默认路径为空(self, runner, project_with_auto_pass_gate, tmp_path):
        feature_dir = tmp_path / "my-feature"
        feature_dir.mkdir()
        # 只写入 android 平台，不写默认路径
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            runner.invoke(cli, [
                "gate", "request", "GATE-R5",
                "--path", str(feature_dir),
                "--platform", "android",
            ])
        # 读取默认路径，应提示无状态
        with patch("driving_cli.commands.gate.find_project_root",
                   return_value=project_with_auto_pass_gate):
            result = runner.invoke(cli, [
                "gate", "status",
                "--path", str(feature_dir),
            ])
        assert result.exit_code == 0
        assert "尚未记录" in result.output
