"""yaml_parser 内联数组解析测试（覆盖无 PyYAML 的降级路径）"""

from driving_cli.utils.yaml_parser import _parse_simple, _parse_value


class TestInlineFlowSequence:
    def test_parse_value_内联数组(self):
        assert _parse_value("[a, b, c]") == ["a", "b", "c"]

    def test_parse_value_空数组(self):
        assert _parse_value("[]") == []

    def test_parse_value_单元素数组(self):
        assert _parse_value("[ui-component]") == ["ui-component"]

    def test_parse_value_带引号元素(self):
        assert _parse_value('["a", "b"]') == ["a", "b"]

    def test_parse_value_普通标量不受影响(self):
        assert _parse_value("ui-component") == "ui-component"
        assert _parse_value("true") is True
        assert _parse_value("42") == 42

    def test_simple_parser_category内联数组(self):
        """简化解析器能把 category: [a, b] 解析为列表"""
        content = "name: xmulti\ncategory: [ui-component, network]"
        result = _parse_simple(content)
        assert result["name"] == "xmulti"
        assert result["category"] == ["ui-component", "network"]

    def test_simple_parser_category单值(self):
        content = "name: ximage\ncategory: ui-component"
        result = _parse_simple(content)
        assert result["category"] == "ui-component"
