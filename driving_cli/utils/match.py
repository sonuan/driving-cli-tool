"""关键词模糊匹配工具"""


def normalize_keywords(keywords: tuple) -> tuple:
    """将关键词元组中的逗号分隔项展开为独立关键词。

    支持空格分隔（click 自动处理）和逗号分隔，例如：
        ("a,b", "c") -> ("a", "b", "c")
        ("a", "b")   -> ("a", "b")

    Args:
        keywords: click 传入的原始关键词元组

    Returns:
        展开后的关键词元组
    """
    return tuple(
        part.strip()
        for kw in keywords
        for part in kw.split(",")
        if part.strip()
    )


def fuzzy_match(text: str, keywords: tuple) -> bool:
    """判断 text 是否匹配任一关键词（不区分大小写的子串匹配）。

    Args:
        text: 待匹配的文本（如 name、description 等）
        keywords: 关键词元组，任一关键词作为子串出现在 text 中即视为匹配

    Returns:
        True 表示匹配成功
    """
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def fuzzy_match_any(fields: tuple, keywords: tuple) -> bool:
    """判断多个字段中是否有任一字段匹配任一关键词。

    Args:
        fields: 待匹配的字段值元组（如 (name, description)）
        keywords: 关键词元组

    Returns:
        True 表示任一字段匹配成功
    """
    return any(fuzzy_match(f, keywords) for f in fields if f)
