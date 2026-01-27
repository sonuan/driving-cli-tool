# 贡献指南

感谢你对 Driving CLI Tool 的关注！我们欢迎所有形式的贡献。

## 如何贡献

### 报告问题

如果你发现了 bug 或有功能建议：

1. 在 [Issues](../../issues) 中搜索，确保问题未被报告
2. 创建新的 Issue，提供详细信息：
   - Bug 报告：复现步骤、预期行为、实际行为、环境信息
   - 功能建议：使用场景、预期效果、可能的实现方案

### 提交代码

1. **Fork 仓库**
   ```bash
   # 在 GitHub 上 Fork 仓库
   # 克隆你的 Fork
   git clone https://github.com/your-username/driving-cli.git
   cd driving-cli/cli-tool
   ```

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

3. **开发环境设置**
   ```bash
   # 安装开发依赖
   pip install -e ".[dev]"
   
   # 或使用 requirements.txt
   pip install -r requirements.txt
   ```

4. **编写代码**
   - 遵循项目的代码风格
   - 添加必要的注释（中文）
   - 确保代码通过所有测试
   - 添加新功能的测试用例

5. **运行测试**
   ```bash
   # 运行所有测试
   pytest
   
   # 运行测试并生成覆盖率报告
   pytest --cov=driving --cov-report=html
   
   # 查看覆盖率报告
   open htmlcov/index.html
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "feat: 添加新功能描述"
   # 或
   git commit -m "fix: 修复问题描述"
   ```

   提交信息格式：
   - `feat:` 新功能
   - `fix:` Bug 修复
   - `docs:` 文档更新
   - `style:` 代码格式调整
   - `refactor:` 代码重构
   - `test:` 测试相关
   - `chore:` 构建/工具相关

7. **推送到 Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **创建 Pull Request**
   - 在 GitHub 上创建 Pull Request
   - 填写 PR 模板，说明改动内容
   - 等待代码审查

## 代码规范

### Python 代码风格

- 遵循 [PEP 8](https://pep8.org/) 规范
- 使用 4 个空格缩进
- 行长度不超过 100 字符
- 使用类型注解（Type Hints）

### 注释规范

- 代码注释使用中文
- 文档字符串（docstring）使用中文
- 复杂逻辑必须添加注释说明

### 示例

```python
def get_framework_info(name: str) -> dict:
    """获取框架信息
    
    Args:
        name: 框架名称
        
    Returns:
        dict: 框架信息字典，包含 name、description 等字段
        
    Raises:
        ValueError: 当框架不存在时抛出
    """
    # 从配置文件加载框架列表
    frameworks = load_frameworks()
    
    # 查找指定框架
    for framework in frameworks:
        if framework['name'] == name:
            return framework
    
    raise ValueError(f"框架 {name} 不存在")
```

## 测试规范

### 测试文件组织

```
tests/
├── __init__.py
├── test_config.py          # 配置模块测试
├── test_git_helper.py      # Git 操作测试
├── test_framework.py       # 框架管理测试
└── test_integration.py     # 集成测试
```

### 测试命名

- 测试文件：`test_<module_name>.py`
- 测试类：`Test<ClassName>`
- 测试方法：`test_<function_name>_<scenario>`

### 示例

```python
import pytest
from driving.utils.config import get_driving_dir, is_local_mode

class TestConfig:
    """配置模块测试"""
    
    def test_is_local_mode_with_gitlist(self, tmp_path):
        """测试本地模式检测 - 存在 gitlist.json"""
        # 创建测试目录
        gitlist = tmp_path / "gitlist.json"
        gitlist.write_text("{}")
        
        # 切换到测试目录
        import os
        os.chdir(tmp_path)
        
        # 验证
        assert is_local_mode() is True
    
    def test_is_local_mode_without_gitlist(self, tmp_path):
        """测试本地模式检测 - 不存在 gitlist.json"""
        os.chdir(tmp_path)
        assert is_local_mode() is False
```

## 文档规范

### 更新文档

如果你的改动影响了用户使用方式：

1. 更新 `README.md`
2. 更新 `QUICKSTART.md`
3. 更新 `CHANGELOG.md`
4. 必要时添加新的文档文件

### 文档格式

- 使用 Markdown 格式
- 中文文档使用中文标点
- 代码示例使用语法高亮

## 发布流程

维护者负责发布新版本：

1. 更新版本号（`driving/__init__.py`）
2. 更新 `CHANGELOG.md`
3. 创建 Git tag
4. 发布到 PyPI
5. 创建 GitHub Release

## 获取帮助

如有疑问，可以通过以下方式获取帮助：

- 在 Issue 中提问
- 查看现有文档
- 参考已有的代码实现

## 致谢

感谢所有贡献者的付出！你的贡献让 Driving CLI Tool 变得更好。

---

再次感谢你的贡献！🎉
