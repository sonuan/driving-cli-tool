"""统一的 YAML frontmatter 解析工具

提供从 Markdown 文件中提取 YAML frontmatter 的统一接口。
优先使用 PyYAML（如果可用），否则降级到内置简化解析器。

使用方式：
    from driving_cli.utils.yaml_parser import parse_frontmatter

    # 从文件解析（逐行读取到第二个 --- 即停止，避免加载大文件正文）
    data = parse_frontmatter(Path("SKILL.md"))
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def parse_frontmatter(
    file_path: Path,
    *,
    required_fields: Optional[List[str]] = None,
) -> Optional[Dict]:
    """从 Markdown 文件中解析 YAML frontmatter。

    逐行读取到第二个 --- 即停止，避免加载大文件正文。
    优先使用 PyYAML，不可用时降级到内置简化解析器。

    Args:
        file_path: Markdown 文件路径
        required_fields: 必须存在的字段列表，缺少任一则返回 None

    Returns:
        解析后的字典，解析失败或缺少必填字段时返回 None
    """
    try:
        yaml_lines: List[str] = []
        with file_path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f):
                if lineno == 0:
                    if line.rstrip("\n") != "---":
                        return None
                    continue
                if line.strip() == "---":
                    break
                yaml_lines.append(line)
            else:
                return None  # 未找到结束 ---

        yaml_content = "".join(yaml_lines).strip()

        if not yaml_content:
            return None

        # 优先使用 PyYAML
        if HAS_YAML:
            try:
                data = yaml.safe_load(yaml_content)
                if isinstance(data, dict):
                    result = data
                else:
                    result = _parse_simple(yaml_content)
            except Exception:
                result = _parse_simple(yaml_content)
        else:
            result = _parse_simple(yaml_content)

        if result is None:
            return None

        # 校验必填字段
        if required_fields:
            for field in required_fields:
                if field not in result:
                    return None

        return result
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 内置简化解析器（无 PyYAML 时的降级方案）
# ---------------------------------------------------------------------------


def _parse_simple(yaml_content: str) -> Optional[Dict]:
    """简化的 YAML 解析器，支持：
    - 单行 key: value
    - 多行块标量 key: |
    - 块序列 key:\\n  - item1\\n  - item2
    - 嵌套字典序列（如 urls 列表中的 type/url/title）

    不支持：锚点、别名、流式集合、复杂嵌套等高级 YAML 特性。
    """
    result: Dict = {}
    lines = yaml_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 跳过空行和注释
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # 跳过缩进行（属于上一个字段的内容，不应作为顶层字段解析）
        if line.startswith("  ") or line.startswith("\t"):
            i += 1
            continue

        # 解析顶层 key: value
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()

            if v == "|":
                # 多行块标量
                result[k] = _parse_block_scalar(lines, i + 1)
                i = _skip_block(lines, i + 1)
            elif v == ">" or v == ">-":
                # 折叠块标量（合并为单行）
                block = _parse_block_scalar(lines, i + 1)
                result[k] = " ".join(line for line in block.split("\n") if line)
                i = _skip_block(lines, i + 1)
            elif v:
                # 单行值
                result[k] = _parse_value(v)
                i += 1
            else:
                # 空值，可能是块序列或嵌套结构
                items = _parse_block_sequence(lines, i + 1)
                if items is not None:
                    result[k] = items
                    i = _skip_block(lines, i + 1)
                else:
                    result[k] = ""
                    i += 1
        else:
            i += 1

    return result if result else None


def _parse_block_scalar(lines: List[str], start: int) -> str:
    """解析多行块标量（| 或 >），返回内容字符串。"""
    block_lines: List[str] = []
    i = start

    while i < len(lines):
        line = lines[i]
        if line.startswith("  ") or line.startswith("\t"):
            block_lines.append(line.strip())
            i += 1
        elif line.strip() == "":
            # 空行保留为段落分隔
            block_lines.append("")
            i += 1
        else:
            break

    # 去除首尾空行
    while block_lines and block_lines[-1] == "":
        block_lines.pop()
    while block_lines and block_lines[0] == "":
        block_lines.pop(0)

    return "\n".join(block_lines)


def _skip_block(lines: List[str], start: int) -> int:
    """跳过缩进块，返回块结束后的行号。"""
    i = start
    while i < len(lines):
        line = lines[i]
        if line.startswith("  ") or line.startswith("\t") or line.strip() == "":
            i += 1
        else:
            break
    return i


def _parse_block_sequence(lines: List[str], start: int) -> Optional[List]:
    """尝试解析块序列（- item 格式），返回列表或 None。"""
    i = start
    # 跳过空行
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    if i >= len(lines):
        return None

    # 检查是否是块序列
    first_stripped = lines[i].strip()
    if not first_stripped.startswith("- "):
        return None

    items: List = []
    current_item: Optional[Dict] = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 非缩进行 = 块结束
        if not (line.startswith("  ") or line.startswith("\t")):
            break

        if stripped.startswith("- "):
            # 新的列表项
            if current_item is not None:
                items.append(
                    current_item
                    if len(current_item) > 1 or _is_dict_item(current_item)
                    else _simplify_item(current_item)
                )
            rest = stripped[2:].strip()
            if ":" in rest and not rest.startswith("http"):
                # 字典项的第一个字段
                current_item = {}
                k, _, v = rest.partition(":")
                current_item[k.strip()] = v.strip()
            else:
                # 简单列表项
                current_item = {"_value": rest}
            i += 1
        elif ":" in stripped and current_item is not None and not stripped.startswith("http"):
            # 字典项的后续字段
            k, _, v = stripped.partition(":")
            current_item[k.strip()] = v.strip()
            i += 1
        else:
            i += 1

    # 处理最后一项
    if current_item is not None:
        items.append(
            current_item
            if len(current_item) > 1 or _is_dict_item(current_item)
            else _simplify_item(current_item)
        )

    if not items:
        return None

    # 如果所有项都是简单值，返回字符串列表
    if all(isinstance(item, str) for item in items):
        return items

    return items


def _is_dict_item(item: Dict) -> bool:
    """判断是否是真正的字典项（非简单值包装）。"""
    return "_value" not in item


def _simplify_item(item: Dict):
    """将只有 _value 的字典简化为字符串。"""
    if "_value" in item:
        return item["_value"]
    return item


def _parse_value(v: str) -> Union[str, bool, int, float, List]:
    """解析单行值，尝试转换基本类型。

    额外支持内联流式序列（flow sequence）：``[a, b, c]`` 解析为字符串列表。
    """
    # 内联流式序列 [a, b, c]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",") if item.strip()]
    return _parse_scalar(v)


def _parse_scalar(v: str) -> Union[str, bool, int, float]:
    """解析标量值，尝试转换基本类型。"""
    # 布尔值
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    # 整数
    try:
        return int(v)
    except ValueError:
        pass
    # 浮点数
    try:
        return float(v)
    except ValueError:
        pass
    # 去除引号
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v
