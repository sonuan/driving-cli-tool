"""配置模块 - 定义全局常量和配置"""

import os
from pathlib import Path

import git
from dotenv import load_dotenv

# 加载 .env 文件（从当前目录或父目录查找）
load_dotenv()


def update_env_file(project_root: Path, key: str, value: str):
    """更新项目根目录的 .env 文件

    Args:
        project_root: 项目根目录
        key: 环境变量名
        value: 环境变量值
    """
    from driving.utils.logger import log_info, log_warning

    env_file = project_root / ".env"
    existing_env = {}

    # 读取现有的 .env 文件
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing_env[k.strip()] = v.strip()

    # 更新或添加新的环境变量
    existing_env[key] = value

    # 写入 .env 文件
    with open(env_file, "w", encoding="utf-8") as f:
        f.write("# Driving CLI 配置\n")
        f.write("# 此文件包含项目配置，可以提交到 Git 仓库\n\n")
        for k, v in sorted(existing_env.items()):
            f.write(f"{k}={v}\n")

    # 确保 .env 不在 .gitignore 中（因为这是项目配置，不是敏感信息）
    gitignore_file = project_root / ".gitignore"
    if gitignore_file.exists():
        gitignore_content = gitignore_file.read_text(encoding="utf-8")
        # 如果 .gitignore 中有 .env，给出提示
        if ".env" in gitignore_content.split("\n"):
            log_warning("检测到 .gitignore 中包含 .env")
            log_info("提示：Driving 配置是项目配置（非敏感信息），建议将 .env 提交到仓库")
            log_info("如需提交，请从 .gitignore 中移除 .env")


# ==================== 可配置项 ====================

# Driving 仓库配置
# 优先级：环境变量（无默认值，需要用户指定）
# 示例：export DRIVING_REPO_URL="https://github.com/your-org/driving"
DRIVING_REPO_URL = os.getenv("DRIVING_REPO_URL")

# 更新服务器配置 - version.json 文件的完整 URL
# 优先级：环境变量 > .env 文件 > 默认值
# 示例：export DRIVING_UPDATE_VERSION_URL="https://your-server.com/path/version.json"
# 或在 .env 文件中添加：DRIVING_UPDATE_VERSION_URL=https://your-server.com/path/version.json
DRIVING_UPDATE_VERSION_URL = os.getenv(
    "DRIVING_UPDATE_VERSION_URL",
    "https://raw.githubusercontent.com/sonuan/driving-cli-tool/main/dist/version.json"
)

# 默认提交信息
# 优先级：环境变量 > 默认值
DEFAULT_COMMIT_MESSAGE = os.getenv("DRIVING_DEFAULT_COMMIT_MESSAGE", "update by driving")

# 敏感字段关键词列表（用于 IDE 配置中的敏感信息检测）
# 优先级：环境变量（逗号分隔）> 默认值
_DEFAULT_SENSITIVE_KEYWORDS = [
    "api_key",
    "apikey",
    "api-key",
    "token",
    "access_token",
    "auth_token",
    "secret",
    "password",
    "passwd",
    "credential",
    "auth",
    "authorization",
    "private_key",
    "privatekey",
]

# 从环境变量读取敏感关键词（逗号分隔）
_env_keywords = os.getenv("DRIVING_SENSITIVE_KEYWORDS", "")
if _env_keywords:
    SENSITIVE_KEYWORDS = [k.strip() for k in _env_keywords.split(",") if k.strip()]
else:
    SENSITIVE_KEYWORDS = _DEFAULT_SENSITIVE_KEYWORDS

# ==================== 内部函数 ====================


def _find_project_root() -> Path:
    """查找项目根目录

    从当前目录向上查找，直到找到包含 .driving 目录或 gitlist.json 文件的目录。
    如果都找不到，返回当前目录。

    Returns:
        Path: 项目根目录
    """
    current = Path.cwd()

    # 向上查找，直到找到 .driving 或 gitlist.json
    while current != current.parent:
        if (current / ".driving").exists() or (current / "gitlist.json").exists():
            return current
        current = current.parent

    # 检查根目录
    if (current / ".driving").exists() or (current / "gitlist.json").exists():
        return current

    # 都找不到，返回当前工作目录
    return Path.cwd()


def is_local_mode() -> bool:
    """判断是否为本地模式（项目根目录存在 gitlist.json）

    Returns:
        bool: True 表示本地模式，False 表示标准模式（使用 .driving 目录）
    """
    project_root = _find_project_root()
    return (project_root / "gitlist.json").exists()


def get_driving_dir() -> Path:
    """获取 driving 目录路径

    Returns:
        Path: 本地模式返回项目根目录，标准模式返回 .driving 目录
    """
    project_root = _find_project_root()
    if is_local_mode():
        return project_root
    return project_root / ".driving"


def get_gitlist_file() -> Path:
    """获取 gitlist.json 文件路径

    Returns:
        Path: gitlist.json 文件的完整路径
    """
    return get_driving_dir() / "gitlist.json"


def get_all_gitlist_files() -> list[Path]:
    """获取所有 gitlist.json 文件路径列表

    按优先级顺序返回：
    1. ai-docs-local/gitlist.json（本地项目配置）
    2. ai-docs/gitlist.json（基础框架配置）
    3. gitlist.json（根目录配置，兼容旧版本）

    Returns:
        list[Path]: gitlist.json 文件路径列表（只返回存在的文件）
    """
    driving_dir = get_driving_dir()
    gitlist_files = []

    # 1. ai-docs-local/gitlist.json（本地项目配置，优先级最高）
    local_gitlist = driving_dir / "ai-docs-local" / "gitlist.json"
    if local_gitlist.exists():
        gitlist_files.append(local_gitlist)

    # 2. ai-docs/gitlist.json（基础框架配置）
    ai_docs_gitlist = driving_dir / "ai-docs" / "gitlist.json"
    if ai_docs_gitlist.exists():
        gitlist_files.append(ai_docs_gitlist)

    # 3. gitlist.json（根目录配置，兼容旧版本）
    root_gitlist = driving_dir / "gitlist.json"
    if root_gitlist.exists():
        gitlist_files.append(root_gitlist)

    return gitlist_files


def get_framework_base_dir() -> Path:
    """获取框架仓库存储目录

    Returns:
        Path: 本地模式返回 submodules 目录，标准模式返回 .driving/submodules 目录
    """
    project_root = _find_project_root()
    if is_local_mode():
        return project_root / "submodules"
    return project_root / ".driving" / "submodules"


def check_environment() -> tuple[bool, str]:
    """检查运行环境是否正确配置

    检查项目根目录是否存在 .driving 目录或 gitlist.json 文件。
    如果都不存在，说明环境未配置。

    Returns:
        tuple[bool, str]: (是否配置正确, 错误信息)
    """
    project_root = _find_project_root()
    has_driving = (project_root / ".driving").exists()
    has_gitlist = (project_root / "gitlist.json").exists()

    if not has_driving and not has_gitlist:
        error_msg = (
            "项目根目录未配置 driving 环境。\n"
            f"项目根目录: {project_root}\n"
            "请执行以下操作之一：\n"
            "  1. 执行 'driving install' 安装 .driving submodule\n"
            "  2. 切换到项目根目录（包含 .driving 或 gitlist.json 的目录）"
        )
        return False, error_msg

    return True, ""


# 兼容性：保留旧的常量名称
DRIVING_DIR = get_driving_dir()
GITLIST_FILE = get_gitlist_file()
FRAMEWORK_BASE_DIR = get_framework_base_dir()

# 确保框架目录存在（如果 driving 目录存在的话）
if get_driving_dir().exists():
    get_framework_base_dir().mkdir(parents=True, exist_ok=True)
