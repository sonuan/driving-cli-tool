"""IDE 敏感关键词配置测试

原 test_config.py 测试旧版 driving/utils/config.py（已删除）。
现在测试迁移后的等效功能：
- SENSITIVE_KEYWORDS 已内联到 driving/commands/ide.py
- 路径解析功能已迁移到 driving/utils/config_manager.py（见 test_config_manager.py）
"""

import pytest

from driving_cli.commands.ide import SENSITIVE_KEYWORDS


class TestSensitiveKeywords:
    """敏感关键词配置测试"""

    def test_default_sensitive_keywords_exist(self):
        """默认敏感关键词列表不为空"""
        assert isinstance(SENSITIVE_KEYWORDS, list)
        assert len(SENSITIVE_KEYWORDS) > 0

    def test_common_keywords_present(self):
        """常见敏感关键词应存在"""
        assert "api_key" in SENSITIVE_KEYWORDS
        assert "token" in SENSITIVE_KEYWORDS
        assert "secret" in SENSITIVE_KEYWORDS
        assert "password" in SENSITIVE_KEYWORDS

    def test_keywords_are_lowercase(self):
        """所有关键词应为小写（便于大小写不敏感匹配）"""
        for kw in SENSITIVE_KEYWORDS:
            assert kw == kw.lower(), f"关键词 '{kw}' 不是小写"
