"""仓库名称和 Git URL 验证工具函数的单元测试及属性测试"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from driving.utils.validators import (
    infer_repo_name_from_url,
    validate_git_url,
    validate_repo_name,
)


# ─────────────────────────────────────────────
# validate_repo_name 单元测试
# ─────────────────────────────────────────────

class TestValidateRepoName:
    """validate_repo_name 的具体示例测试"""

    def test_合法名称_纯字母(self):
        assert validate_repo_name("main") is True

    def test_合法名称_字母数字(self):
        assert validate_repo_name("repo123") is True

    def test_合法名称_含连字符(self):
        assert validate_repo_name("my-repo") is True

    def test_合法名称_含下划线(self):
        assert validate_repo_name("my_repo") is True

    def test_合法名称_单字符(self):
        assert validate_repo_name("a") is True

    def test_合法名称_数字开头(self):
        assert validate_repo_name("1repo") is True

    def test_合法名称_64字符(self):
        assert validate_repo_name("a" * 64) is True

    def test_非法名称_空字符串(self):
        assert validate_repo_name("") is False

    def test_非法名称_超过64字符(self):
        assert validate_repo_name("a" * 65) is False

    def test_非法名称_含空格(self):
        assert validate_repo_name("my repo") is False

    def test_非法名称_含斜杠(self):
        assert validate_repo_name("my/repo") is False

    def test_非法名称_含中文(self):
        assert validate_repo_name("仓库") is False

    def test_非法名称_连字符开头(self):
        assert validate_repo_name("-repo") is False

    def test_非法名称_下划线开头(self):
        assert validate_repo_name("_repo") is False

    def test_非法名称_含点号(self):
        assert validate_repo_name("my.repo") is False

    def test_非法名称_含at符号(self):
        assert validate_repo_name("my@repo") is False


# ─────────────────────────────────────────────
# validate_git_url 单元测试
# ─────────────────────────────────────────────

class TestValidateGitUrl:
    """validate_git_url 的具体示例测试"""

    def test_合法_https_带git后缀(self):
        assert validate_git_url("https://github.com/user/repo.git") is True

    def test_合法_https_不带git后缀(self):
        assert validate_git_url("https://github.com/user/repo") is True

    def test_合法_http(self):
        assert validate_git_url("http://github.com/user/repo.git") is True

    def test_合法_ssh_带git后缀(self):
        assert validate_git_url("git@github.com:user/repo.git") is True

    def test_合法_ssh_不带git后缀(self):
        assert validate_git_url("git@github.com:user/repo") is True

    def test_合法_gitlab_ssh(self):
        assert validate_git_url("git@gitlab.com:org/project.git") is True

    def test_合法_https_子路径(self):
        assert validate_git_url("https://github.com/org/sub/repo.git") is True

    def test_非法_空字符串(self):
        assert validate_git_url("") is False

    def test_非法_纯路径(self):
        assert validate_git_url("/local/path/repo") is False

    def test_非法_无协议(self):
        assert validate_git_url("github.com/user/repo") is False

    def test_非法_ftp协议(self):
        assert validate_git_url("ftp://github.com/user/repo") is False

    def test_非法_仅域名(self):
        assert validate_git_url("https://github.com") is False

    def test_非法_空白字符串(self):
        assert validate_git_url("   ") is False


# ─────────────────────────────────────────────
# infer_repo_name_from_url 单元测试
# ─────────────────────────────────────────────

class TestInferRepoNameFromUrl:
    """infer_repo_name_from_url 的具体示例测试"""

    def test_https_带git后缀(self):
        assert infer_repo_name_from_url("https://github.com/user/my-repo.git") == "my-repo"

    def test_https_不带git后缀(self):
        assert infer_repo_name_from_url("https://github.com/user/my-repo") == "my-repo"

    def test_ssh_带git后缀(self):
        assert infer_repo_name_from_url("git@github.com:user/my-repo.git") == "my-repo"

    def test_ssh_不带git后缀(self):
        assert infer_repo_name_from_url("git@github.com:user/my-repo") == "my-repo"

    def test_含点号的名称(self):
        # 点号应被替换为连字符
        result = infer_repo_name_from_url("https://github.com/user/my.repo.git")
        assert validate_repo_name(result) is True

    def test_含特殊字符的名称(self):
        # 特殊字符应被替换为连字符
        result = infer_repo_name_from_url("https://github.com/user/my_repo-v2.git")
        assert validate_repo_name(result) is True

    def test_结果满足合法性规则(self):
        urls = [
            "https://github.com/user/driving-cli-tool.git",
            "git@github.com:org/private-repo.git",
            "https://gitlab.com/team/project",
        ]
        for url in urls:
            result = infer_repo_name_from_url(url)
            assert validate_repo_name(result), f"URL {url!r} 推断出非法名称: {result!r}"

    def test_末尾斜杠(self):
        result = infer_repo_name_from_url("https://github.com/user/repo/")
        assert validate_repo_name(result) is True


# ─────────────────────────────────────────────
# 属性测试
# ─────────────────────────────────────────────

# Feature: multi-repo-support, Property 3: 仓库名称合法性验证
# 对于任意不满足正则的字符串，validate_repo_name 应返回 False
@given(
    st.text(
        alphabet=st.characters(
            blacklist_categories=('Lu', 'Ll', 'Nd'),  # 排除大写字母、小写字母、数字
            blacklist_characters='-_',
        ),
        min_size=1,
        max_size=64,
    )
)
@settings(max_examples=200)
def test_property3_非法字符名称被拒绝(name: str):
    """
    **Validates: Requirements 3.2**

    Property 3：仓库名称合法性验证
    包含非法字符（非字母数字连字符下划线）的名称应被拒绝。
    """
    # 确保名称中确实含有非法字符（不是纯合法字符）
    import re
    if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', name) and len(name) <= 64:
        # 如果碰巧生成了合法名称，跳过
        return
    assert validate_repo_name(name) is False


# Feature: multi-repo-support, Property 9: URL 推断名称合法性
# 对于任意合法的 Git URL，推断出的名称应满足 validate_repo_name
_REPO_SEGMENT = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-_'),
    min_size=1,
    max_size=30,
).filter(lambda s: s[0].isalnum())

_USER_SEGMENT = st.text(
    alphabet=st.sampled_from('abcdefghijklmnopqrstuvwxyz0123456789-'),
    min_size=1,
    max_size=20,
).filter(lambda s: s[0].isalnum())

_HOST = st.sampled_from(['github.com', 'gitlab.com', 'bitbucket.org', 'example.com'])

_HTTPS_URL = st.builds(
    lambda host, user, repo, suffix: f"https://{host}/{user}/{repo}{suffix}",
    host=_HOST,
    user=_USER_SEGMENT,
    repo=_REPO_SEGMENT,
    suffix=st.sampled_from(['.git', '']),
)

_SSH_URL = st.builds(
    lambda host, user, repo, suffix: f"git@{host}:{user}/{repo}{suffix}",
    host=_HOST,
    user=_USER_SEGMENT,
    repo=_REPO_SEGMENT,
    suffix=st.sampled_from(['.git', '']),
)

_GIT_URL = st.one_of(_HTTPS_URL, _SSH_URL)


@given(_GIT_URL)
@settings(max_examples=200)
def test_property9_url推断名称合法性(url: str):
    """
    **Validates: Requirements 2.3**

    Property 9：URL 推断名称合法性
    对于任意合法的 Git URL，infer_repo_name_from_url 推断出的名称应满足 validate_repo_name。
    """
    result = infer_repo_name_from_url(url)
    assert validate_repo_name(result), (
        f"URL {url!r} 推断出非法名称: {result!r}"
    )
