"""Template_Renderer 单元测试

测试 TemplateRenderer 的模板变量渲染功能，覆盖：
- path 变量替换
- context 嵌套字段替换
- state 字段替换
- 不存在变量替换为空字符串
- render_lines 方法
"""

import pytest

from driving_cli.gate.template_renderer import TemplateRenderer


class TestRenderPathVariable:
    """测试 {{path}} 变量替换 - Requirements 5.1"""

    def test_替换path变量(self):
        renderer = TemplateRenderer(
            path="features/login-page", context={}, state={}
        )
        result = renderer.render("目录: {{path}}")
        assert result == "目录: features/login-page"

    def test_多个path变量(self):
        renderer = TemplateRenderer(
            path="features/login-page", context={}, state={}
        )
        result = renderer.render("{{path}}/docs 和 {{path}}/src")
        assert result == "features/login-page/docs 和 features/login-page/src"

    def test_path变量带空格(self):
        renderer = TemplateRenderer(
            path="features/login-page", context={}, state={}
        )
        result = renderer.render("{{ path }}")
        assert result == "features/login-page"


class TestRenderContextVariable:
    """测试 {{context.xxx}} 变量替换 - Requirements 5.2"""

    def test_替换context顶层字段(self):
        renderer = TemplateRenderer(
            path="", context={"task_count": 12}, state={}
        )
        result = renderer.render("任务数: {{context.task_count}}")
        assert result == "任务数: 12"

    def test_替换context嵌套字段(self):
        renderer = TemplateRenderer(
            path="",
            context={"project": {"name": "my-app", "version": "1.0"}},
            state={},
        )
        result = renderer.render("项目: {{context.project.name}}")
        assert result == "项目: my-app"

    def test_替换context深层嵌套(self):
        renderer = TemplateRenderer(
            path="",
            context={"a": {"b": {"c": "deep_value"}}},
            state={},
        )
        result = renderer.render("值: {{context.a.b.c}}")
        assert result == "值: deep_value"

    def test_context字符串值(self):
        renderer = TemplateRenderer(
            path="", context={"name": "hello"}, state={}
        )
        result = renderer.render("{{context.name}}")
        assert result == "hello"


class TestRenderStateVariable:
    """测试 {{state.xxx}} 变量替换 - Requirements 5.3"""

    def test_替换state字段(self):
        renderer = TemplateRenderer(
            path="", context={}, state={"last_result": "pass"}
        )
        result = renderer.render("上次结果: {{state.last_result}}")
        assert result == "上次结果: pass"

    def test_替换state数值字段(self):
        renderer = TemplateRenderer(
            path="", context={}, state={"request_count": 5}
        )
        result = renderer.render("请求次数: {{state.request_count}}")
        assert result == "请求次数: 5"

    def test_替换state嵌套字段(self):
        renderer = TemplateRenderer(
            path="", context={}, state={"info": {"status": "active"}}
        )
        result = renderer.render("状态: {{state.info.status}}")
        assert result == "状态: active"


class TestRenderMissingVariable:
    """测试不存在变量替换为空字符串 - Requirements 5.4"""

    def test_context字段不存在(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        result = renderer.render("值: {{context.nonexistent}}")
        assert result == "值: "

    def test_state字段不存在(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        result = renderer.render("值: {{state.nonexistent}}")
        assert result == "值: "

    def test_嵌套路径中间层不存在(self):
        renderer = TemplateRenderer(
            path="", context={"a": "not_a_dict"}, state={}
        )
        result = renderer.render("{{context.a.b.c}}")
        assert result == ""

    def test_未知根变量替换为空(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        result = renderer.render("{{unknown.field}}")
        assert result == ""

    def test_单个未知token替换为空(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        result = renderer.render("{{something}}")
        assert result == ""


class TestRenderMixed:
    """测试混合变量渲染"""

    def test_混合path_context_state(self):
        renderer = TemplateRenderer(
            path="features/login",
            context={"task_count": 3},
            state={"last_result": "amend"},
        )
        template = "路径={{path}}, 任务={{context.task_count}}, 结果={{state.last_result}}"
        result = renderer.render(template)
        assert result == "路径=features/login, 任务=3, 结果=amend"

    def test_无模板变量时原样返回(self):
        renderer = TemplateRenderer(path="x", context={}, state={})
        result = renderer.render("没有变量的普通文本")
        assert result == "没有变量的普通文本"

    def test_空字符串渲染(self):
        renderer = TemplateRenderer(path="x", context={}, state={})
        result = renderer.render("")
        assert result == ""


class TestRenderLines:
    """测试 render_lines 方法"""

    def test_渲染多行模板(self):
        renderer = TemplateRenderer(
            path="features/login",
            context={"name": "登录页"},
            state={},
        )
        lines = [
            "# {{context.name}}",
            "路径: {{path}}",
            "普通行",
        ]
        result = renderer.render_lines(lines)
        assert result == "# 登录页\n路径: features/login\n普通行"

    def test_空列表返回空字符串(self):
        renderer = TemplateRenderer(path="x", context={}, state={})
        result = renderer.render_lines([])
        assert result == ""

    def test_单行列表(self):
        renderer = TemplateRenderer(path="hello", context={}, state={})
        result = renderer.render_lines(["{{path}}"])
        assert result == "hello"


class TestRenderVarsVariable:
    """测试 {{$vars.xxx}} CLI 内部预计算变量替换"""

    def test_渲染已注入的vars变量(self):
        renderer = TemplateRenderer(
            path="/features/login",
            context={},
            state={},
            vars={"$vars.platform_dir": "/features/login/docs/android"},
        )
        result = renderer.render("路径: {{$vars.platform_dir}}")
        assert result == "路径: /features/login/docs/android"

    def test_渲染多个vars变量(self):
        renderer = TemplateRenderer(
            path="/features/login",
            context={},
            state={},
            vars={
                "$vars.platform_dir": "/features/login/docs/android",
                "$vars.review_dir": "/features/login/docs/android/review",
                "$vars.state_file": "/features/login/docs/android/state.json",
            },
        )
        result = renderer.render(
            "{{$vars.platform_dir}} / {{$vars.review_dir}} / {{$vars.state_file}}"
        )
        assert result == (
            "/features/login/docs/android"
            " / /features/login/docs/android/review"
            " / /features/login/docs/android/state.json"
        )

    def test_vars未注入时返回空字符串(self):
        renderer = TemplateRenderer(path="", context={}, state={})
        result = renderer.render("{{$vars.missing}}")
        assert result == ""

    def test_vars为None时返回空字符串(self):
        renderer = TemplateRenderer(path="", context={}, state={}, vars=None)
        result = renderer.render("{{$vars.platform_dir}}")
        assert result == ""

    def test_vars变量和其他变量混合渲染(self):
        renderer = TemplateRenderer(
            path="/features/login",
            context={"stage": "requirement"},
            state={},
            vars={"$vars.state_file": "/features/login/docs/android/state.json"},
        )
        result = renderer.render(
            "将 `{{$vars.state_file}}` 中 `stages.{{context.stage}}.status` 更新为 `completed`"
        )
        assert result == (
            "将 `/features/login/docs/android/state.json` 中 "
            "`stages.requirement.status` 更新为 `completed`"
        )

    def test_vars不影响同名context变量(self):
        """$vars.xxx 前缀与 context.xxx 独立，互不干扰"""
        renderer = TemplateRenderer(
            path="",
            context={"platform_dir": "context_value"},
            state={},
            vars={"$vars.platform_dir": "vars_value"},
        )
        assert renderer.render("{{$vars.platform_dir}}") == "vars_value"
        assert renderer.render("{{context.platform_dir}}") == "context_value"

    def test_旧格式不以vars前缀则不匹配(self):
        """不带 $vars. 前缀的旧格式无法匹配"""
        renderer = TemplateRenderer(
            path="",
            context={},
            state={},
            vars={"$vars.platform_dir": "correct_value"},
        )
        # 旧格式 {{$platform_dir}} 不能匹配到新 key
        result = renderer.render("{{$platform_dir}}")
        assert result == ""

    def test_vars键不以dollar_vars开头时不匹配(self):
        """vars 中不以 $vars. 开头的键，通过 {{$vars.xxx}} 无法匹配"""
        renderer = TemplateRenderer(
            path="",
            context={},
            state={},
            vars={"platform_dir": "should_not_match"},
        )
        result = renderer.render("{{$vars.platform_dir}}")
        assert result == ""


class TestBuildGateVars:
    """测试 _build_gate_vars 内部常量计算函数"""

    def test_有platform时platform_dir包含platform(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "android")
        assert vars_["$vars.platform_dir"] == "/features/login/docs/android"

    def test_有platform时platform_dir正确拼接(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "android")
        assert vars_["$vars.platform_dir"] == "/features/login/docs/android"

    def test_有platform时owner_dir默认等于platform_dir(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "android")
        assert vars_["$vars.owner_dir"] == vars_["$vars.platform_dir"]

    def test_无platform时platform_dir为docs(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "")
        assert vars_["$vars.platform_dir"] == "/features/login/docs"

    def test_无platform时owner_dir等于platform_dir(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "")
        assert vars_["$vars.owner_dir"] == "/features/login/docs"

    def test_无platform时owner_dir在docs下(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/features/login", "")
        assert vars_["$vars.owner_dir"] == "/features/login/docs"

    def test_不同platform产生不同paths(self):
        from driving_cli.commands.gate import _build_gate_vars
        android = _build_gate_vars("/p", "android")
        ios = _build_gate_vars("/p", "iOS")
        assert android["$vars.platform_dir"] != ios["$vars.platform_dir"]
        assert android["$vars.owner_dir"] != ios["$vars.owner_dir"]

    def test_三个常量key全部存在(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/p", "android")
        assert "$vars.platform_dir" in vars_
        assert "$vars.owner_dir" in vars_

    def test_path和platform组合正确拼接(self):
        from driving_cli.commands.gate import _build_gate_vars
        vars_ = _build_gate_vars("/workspace/feature-x", "harmony")
        assert vars_["$vars.platform_dir"] == "/workspace/feature-x/docs/harmony"
        assert vars_["$vars.owner_dir"].startswith("/workspace/feature-x/docs/harmony")
