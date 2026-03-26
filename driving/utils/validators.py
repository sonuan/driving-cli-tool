"""仓库名称和 Git URL 合法性验证工具函数"""

import re
from urllib.parse import urlparse

# 仓库名称合法性正则：以字母或数字开头，只允许字母、数字、连字符、下划线，长度 1-64
_REPO_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')

# 支持的 Git URL 格式
# HTTPS: https://github.com/user/repo.git
# SSH:   git@github.com:user/repo.git
_HTTPS_URL_PATTERN = re.compile(
    r'^https?://[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+$'
)
_SSH_URL_PATTERN = re.compile(
    r'^git@[a-zA-Z0-9._-]+:[a-zA-Z0-9._/-]+$'
)

# 非法字符替换为连字符
_INVALID_CHAR_PATTERN = re.compile(r'[^a-zA-Z0-9_-]')

# 开头非法字符（非字母数字）
_LEADING_INVALID_PATTERN = re.compile(r'^[^a-zA-Z0-9]+')


def validate_repo_name(name: str) -> bool:
    """
    校验仓库名称是否合法。

    规则：
    - 只允许字母、数字、连字符（-）、下划线（_）
    - 必须以字母或数字开头
    - 长度 1-64 个字符

    :param name: 待校验的仓库名称
    :return: 合法返回 True，否则返回 False
    """
    if not name or len(name) > 64:
        return False
    return bool(_REPO_NAME_PATTERN.match(name))


def infer_repo_name_from_url(url: str) -> str:
    """
    从 Git URL 中推断仓库名称。

    推断规则：
    1. 提取 URL 最后一个路径段
    2. 去除 .git 后缀
    3. 将非法字符替换为连字符
    4. 去除开头的非法字符
    5. 截断至 64 个字符
    6. 若结果为空，返回 "repo"

    支持格式：
    - HTTPS: https://github.com/user/repo.git
    - SSH:   git@github.com:user/repo.git
    - 无 .git 后缀的 URL

    :param url: Git 仓库 URL
    :return: 推断出的合法仓库名称
    """
    url = url.strip()

    # 处理 SSH 格式：git@github.com:user/repo.git
    if url.startswith('git@'):
        # 取冒号后面的路径部分
        colon_idx = url.find(':')
        if colon_idx != -1:
            path_part = url[colon_idx + 1:]
        else:
            path_part = url
    else:
        # 处理 HTTPS 格式，提取路径部分
        try:
            parsed = urlparse(url)
            path_part = parsed.path
        except Exception:
            path_part = url

    # 提取最后一个路径段
    # 去除末尾斜杠后再分割
    path_part = path_part.rstrip('/')
    last_segment = path_part.split('/')[-1]

    # 去除 .git 后缀
    if last_segment.endswith('.git'):
        last_segment = last_segment[:-4]

    # 将非法字符替换为连字符
    name = _INVALID_CHAR_PATTERN.sub('-', last_segment)

    # 去除开头的非法字符（非字母数字）
    name = _LEADING_INVALID_PATTERN.sub('', name)

    # 去除末尾连字符
    name = name.rstrip('-')

    # 截断至 64 个字符
    name = name[:64]

    # 若结果为空或不合法，返回默认名称
    if not name or not validate_repo_name(name):
        return 'repo'

    return name


def validate_git_url(url: str) -> bool:
    """
    校验 Git URL 格式是否合法。

    支持格式：
    - HTTPS: https://github.com/user/repo 或 https://github.com/user/repo.git
    - SSH:   git@github.com:user/repo 或 git@github.com:user/repo.git

    :param url: 待校验的 Git URL
    :return: 合法返回 True，否则返回 False
    """
    if not url or not url.strip():
        return False

    url = url.strip()

    # 校验 SSH 格式
    if url.startswith('git@'):
        return bool(_SSH_URL_PATTERN.match(url))

    # 校验 HTTPS 格式
    if url.startswith('http://') or url.startswith('https://'):
        return bool(_HTTPS_URL_PATTERN.match(url))

    return False
