"""配置管理器

负责读写 driving.config.json / driving.power.json，提供仓库配置的增删查改及路径辅助方法。

模式说明：
- 传统模式：项目根目录存在 driving.config.json，直接读写该文件（原有行为不变）。
- Power 模式：项目根目录存在 driving.power.json，从各 power 目录下的 driving.config.json
  合并出一份只读的 DrivingConfig 供读取；写入时需指定 power name，写入对应 power 的文件。
  降级规则：某个 power 的 driving.config.json 不存在时跳过该 power；
  若所有 power 均无有效配置，自动降级读取项目根目录的 driving.config.json。
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from driving_cli.models.config import DrivingConfig, RepoConfig
from driving_cli.models.power_config import PowerConfig, PowerEntry

# 配置文件名称
CONFIG_FILE_NAME = "driving.config.json"

# power 配置文件名称
POWER_FILE_NAME = "driving.power.json"

# ai-driving 根目录名称
AI_DRIVING_DIR_NAME = "ai-driving"

# 默认配置值
DEFAULT_VERSION = "2"
DEFAULT_COMMIT_MESSAGE = "update by driving"
DEFAULT_UPDATE_VERSION_URL = ""


# ==================== 单值字段合并策略 ====================

# 这些字段在多个 power 中必须完全相同，否则报错
_CONFLICT_CHECK_FIELDS = (
    "default_commit_message",
    "update_version_url",
    "gate_webhook",
    "agent_webhook",
    "user_prompt",
    "check_sample_rate",
)


def _merge_configs(configs: List[DrivingConfig], power_names: List[str]) -> DrivingConfig:
    """将多个 DrivingConfig 合并为一个。

    合并规则：
    - repos：按 name 去重，先出现的 power 优先（保留第一个）
    - 单值字段（webhook、url 等）：所有 power 中非空值必须相同，否则抛出 ValueError
    - version：取第一个 power 的值
    """
    if not configs:
        raise ValueError("没有可合并的配置")

    # --- repos 合并（按 name 去重，先出现优先）---
    merged_repos: List[RepoConfig] = []
    seen_names: set = set()
    for cfg in configs:
        for repo in cfg.repos:
            if repo.name not in seen_names:
                merged_repos.append(repo)
                seen_names.add(repo.name)

    # --- 单值字段冲突检测 ---
    def _get_field(cfg: DrivingConfig, field: str):
        return getattr(cfg, field)

    result_fields = {}
    for field in _CONFLICT_CHECK_FIELDS:
        values = [(_get_field(cfg, field), name) for cfg, name in zip(configs, power_names)]
        # 过滤空值（空字符串 / 默认值不参与冲突检测）
        non_default = [(v, n) for v, n in values if v not in ("", None)]
        if not non_default:
            # 全部为空/None，取第一个 config 的值
            result_fields[field] = _get_field(configs[0], field)
            continue
        unique_vals = {v for v, _ in non_default}
        if len(unique_vals) > 1:
            conflict_detail = ", ".join(f"{n}={repr(v)}" for v, n in non_default)
            raise ValueError(
                f"Power 配置冲突：字段 '{field}' 在多个 power 中值不同 ({conflict_detail})，"
                f"请统一后重试"
            )
        result_fields[field] = non_default[0][0]

    return DrivingConfig(
        version=configs[0].version,
        repos=merged_repos,
        default_commit_message=result_fields["default_commit_message"] or DEFAULT_COMMIT_MESSAGE,
        update_version_url=result_fields["update_version_url"] or DEFAULT_UPDATE_VERSION_URL,
        user_prompt=result_fields["user_prompt"] or "",
        check_sample_rate=result_fields["check_sample_rate"],
        gate_webhook=result_fields["gate_webhook"] or "",
        agent_webhook=result_fields["agent_webhook"] or "",
    )


def find_project_root() -> Path:
    """向上查找项目根目录

    从当前目录向上遍历，直到找到包含 driving.config.json、driving.power.json 或 ai-driving/ 的目录。
    如果都找不到，返回当前工作目录。

    Returns:
        Path: 项目根目录路径
    """
    current = Path.cwd()

    # 向上查找，直到文件系统根目录
    while current != current.parent:
        if (
            (current / CONFIG_FILE_NAME).exists()
            or (current / POWER_FILE_NAME).exists()
            or (current / AI_DRIVING_DIR_NAME).exists()
        ):
            return current
        current = current.parent

    # 检查根目录本身
    if (
        (current / CONFIG_FILE_NAME).exists()
        or (current / POWER_FILE_NAME).exists()
        or (current / AI_DRIVING_DIR_NAME).exists()
    ):
        return current

    # 都找不到，返回当前工作目录
    return Path.cwd()


class PowerManager:
    """Power 配置管理器

    负责读写 driving.power.json，以及加载各 power 目录下的 driving.config.json。
    """

    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._power_file = project_root / POWER_FILE_NAME

    def exists(self) -> bool:
        """driving.power.json 是否存在"""
        return self._power_file.exists()

    def load_power_config(self) -> PowerConfig:
        """加载 driving.power.json"""
        try:
            raw = self._power_file.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"driving.power.json 读取失败：{e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"driving.power.json 格式错误：{e}") from e

        try:
            return PowerConfig.from_dict(data)
        except (KeyError, ValueError) as e:
            raise ValueError(f"driving.power.json 格式错误：{e}") from e

    def save_power_config(self, power_cfg: PowerConfig) -> None:
        """保存 driving.power.json"""
        self._power_file.parent.mkdir(parents=True, exist_ok=True)
        self._power_file.write_text(
            json.dumps(power_cfg.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_driving_config_for(self, entry: PowerEntry) -> DrivingConfig:
        """加载指定 power 目录下的 driving.config.json"""
        config_path = self._project_root / entry.path / CONFIG_FILE_NAME
        if not config_path.exists():
            raise ValueError(
                f"Power '{entry.name}' 的配置文件不存在：{config_path}，"
                f"该目录下必须包含 driving.config.json 才能作为 power"
            )
        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return DrivingConfig.from_dict(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Power '{entry.name}' 的配置文件格式错误：{e}") from e
        except (KeyError, ValueError) as e:
            raise ValueError(f"Power '{entry.name}' 的配置文件格式错误：{e}") from e

    def load_merged_config(self) -> Optional[DrivingConfig]:
        """加载并合并所有 power 的配置。

        合并规则：
        - driving.config.json 不存在的 power 跳过（不报错）
        - 有效 power > 0：合并后返回 DrivingConfig
        - 有效 power = 0（全部缺失）：返回 None，由调用方降级处理

        Returns:
            DrivingConfig：合并结果；None 表示所有 power 均无有效配置，需降级
        """
        power_cfg = self.load_power_config()
        if not power_cfg.powers:
            raise ValueError("driving.power.json 中没有配置任何 power")

        configs = []
        names = []
        for entry in power_cfg.powers:
            config_path = self._project_root / entry.path / CONFIG_FILE_NAME
            if not config_path.exists():
                # 跳过缺失的 power，不报错
                continue
            try:
                raw = config_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                cfg = DrivingConfig.from_dict(data)
                configs.append(cfg)
                names.append(entry.name)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                raise ValueError(f"Power '{entry.name}' 的配置文件格式错误：{e}") from e

        if not configs:
            # 所有 power 均无有效配置，返回 None 触发降级
            return None

        return _merge_configs(configs, names)

    def get_config_manager_for(self, power_name: str) -> "ConfigManager":
        """返回指定 power 的 ConfigManager（用于写入操作）"""
        power_cfg = self.load_power_config()
        for entry in power_cfg.powers:
            if entry.name == power_name:
                power_root = self._project_root / entry.path
                return ConfigManager(power_root)
        raise ValueError(
            f"Power '{power_name}' 不存在，使用 'driving power list' 查看已配置的 power"
        )

    def get_default_config_manager(self) -> "ConfigManager":
        """返回第一个 power 的 ConfigManager（--power 未指定时的默认写入目标）"""
        power_cfg = self.load_power_config()
        if not power_cfg.powers:
            raise ValueError("driving.power.json 中没有配置任何 power")
        first = power_cfg.powers[0]
        return ConfigManager(self._project_root / first.path)

    def add_power_local(self, entry: PowerEntry) -> None:
        """添加一个本地 power 条目（目录已存在，直接注册）"""
        if self.exists():
            power_cfg = self.load_power_config()
        else:
            power_cfg = PowerConfig(powers=[])

        if any(p.name == entry.name for p in power_cfg.powers):
            raise ValueError(f"Power '{entry.name}' 已存在")

        # 校验目标目录下有 driving.config.json
        config_path = self._project_root / entry.path / CONFIG_FILE_NAME
        if not config_path.exists():
            raise ValueError(f"路径 '{entry.path}' 下不存在 driving.config.json，无法作为 power")

        power_cfg.powers.append(entry)
        self.save_power_config(power_cfg)

    def add_power_remote(self, entry: PowerEntry, git_root: Path) -> None:
        """添加一个远程 power（git submodule clone），然后注册到 driving.power.json

        调用前应已在命令层完成 name 重复检查和目录存在检查（--force 处理）。

        Args:
            entry: PowerEntry，url 必须有值
            git_root: 主项目 git 根目录（用于执行 submodule add）

        Raises:
            ValueError: URL 无效、driving.config.json 不存在等
        """
        import subprocess as _sp

        if not entry.url:
            raise ValueError("远程 power 必须提供 url")

        if self.exists():
            power_cfg = self.load_power_config()
        else:
            power_cfg = PowerConfig(powers=[])

        if any(p.name == entry.name for p in power_cfg.powers):
            raise ValueError(f"Power '{entry.name}' 已存在，使用 --force 覆盖")

        # 计算相对于 git 根目录的 submodule 路径
        abs_path = self._project_root / entry.path
        try:
            submodule_path = str(abs_path.relative_to(git_root))
        except ValueError:
            submodule_path = entry.path

        # 清理残留工作目录（--force 场景下目录可能非空）
        if abs_path.exists() and not abs_path.is_symlink():
            import shutil

            shutil.rmtree(abs_path)

        # 清理残留 .git/modules 数据
        self._cleanup_stale_git_modules(git_root, submodule_path)

        # git submodule add
        try:
            result = _sp.run(
                ["git", "submodule", "add", "--force", entry.url, submodule_path],
                cwd=str(git_root),
                stderr=_sp.PIPE,
                text=True,
            )
            if result.returncode != 0:
                raise _sp.CalledProcessError(
                    result.returncode, "git submodule add", stderr=result.stderr
                )
        except _sp.CalledProcessError as e:
            # 主仓库尚无 commit 时 checkout 会失败，但 clone 已完成
            gitmodules = git_root / ".gitmodules"
            if gitmodules.exists() and submodule_path in gitmodules.read_text(encoding="utf-8"):
                pass  # clone 成功，继续
            else:
                stderr_msg = (e.stderr or "").strip()
                detail = f"\n{stderr_msg}" if stderr_msg else ""
                raise ValueError(
                    f"git submodule add 失败（returncode={e.returncode}）{detail}"
                ) from e

        # 设置 ignore = all，避免主项目 git status 显示 power 内部变更
        self._set_submodule_ignore(git_root, submodule_path)

        power_cfg.powers.append(entry)
        self.save_power_config(power_cfg)

    def pull_power(self, name: str) -> bool:
        """拉取指定远程 power 的最新内容

        Returns:
            True 表示成功，False 表示跳过（本地 power 或目录不存在）

        Raises:
            ValueError: power 不存在
        """
        import subprocess as _sp

        power_cfg = self.load_power_config()
        entry = next((p for p in power_cfg.powers if p.name == name), None)
        if entry is None:
            raise ValueError(f"Power '{name}' 不存在")

        if entry.type == "local":
            return False  # 本地 power 不需要 pull

        repo_dir = self._project_root / entry.path
        if not repo_dir.exists():
            return False

        try:
            result = _sp.run(
                ["git", "pull", "--quiet"],
                cwd=str(repo_dir),
                stdout=_sp.DEVNULL,
                stderr=_sp.PIPE,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr_msg = (result.stderr or "").strip()
                detail = f"：{stderr_msg}" if stderr_msg else ""
                raise ValueError(f"git pull 失败（returncode={result.returncode}）{detail}")
            # 上报：power pull 成功
            try:
                import git as _git

                from driving_cli.utils.op_reporter import report_op_event

                _branch = ""
                try:
                    _repo_obj = _git.Repo(repo_dir)
                    if not _repo_obj.head.is_detached:
                        _branch = _repo_obj.active_branch.name
                except Exception:
                    pass
                report_op_event(
                    operation="power_pulled",
                    description=f"power '{name}' 自动拉取成功",
                    extra={
                        "repo_name": name,
                        "branch": _branch or None,
                        "trigger": "load_auto_pull",
                    },
                    silent=True,
                )
            except Exception:
                pass
            return True
        except _sp.TimeoutExpired:
            raise ValueError("git pull 超时，请检查网络连接或 SSH 配置")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"git pull 失败：{e}") from e

    def check_power_updates(self) -> list:
        """检查所有远程 power 是否有更新（纯本地对比，不 fetch）

        Returns:
            有更新的 PowerEntry 列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from driving_cli.commands.check import _compare_local_remote

        if not self.exists():
            return []

        try:
            power_cfg = self.load_power_config()
        except ValueError:
            return []

        candidates = []
        for entry in power_cfg.powers:
            if entry.type != "remote":
                continue
            repo_dir = self._project_root / entry.path
            if not (repo_dir / ".git").exists():
                continue
            candidates.append((entry, repo_dir))

        if not candidates:
            return []

        updatable = []
        with ThreadPoolExecutor(max_workers=min(len(candidates), 8)) as executor:
            future_to_entry = {
                executor.submit(_compare_local_remote, repo_dir): entry
                for entry, repo_dir in candidates
            }
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result is True:
                    updatable.append(entry)

        # 保持原始顺序
        order = {entry.name: i for i, (entry, _) in enumerate(candidates)}
        updatable.sort(key=lambda e: order.get(e.name, 0))

        return updatable

    def remove_power(self, name: str) -> None:
        """移除一个 power 条目（仅修改 driving.power.json，不删除目录）"""
        power_cfg = self.load_power_config()
        original = len(power_cfg.powers)
        power_cfg.powers = [p for p in power_cfg.powers if p.name != name]
        if len(power_cfg.powers) == original:
            raise ValueError(f"Power '{name}' 不存在")
        self.save_power_config(power_cfg)

    @staticmethod
    def _cleanup_stale_git_modules(git_root: Path, submodule_path: str) -> None:
        """清理残留的 .git/modules 数据"""
        import shutil

        modules_dir = git_root / ".git" / "modules"
        parts = Path(submodule_path).parts
        for depth in range(len(parts), 0, -1):
            partial = Path(*parts[:depth])
            modules_path = modules_dir / partial
            work_path = git_root / partial
            work_empty = not work_path.exists() or (
                work_path.is_dir() and not any(work_path.iterdir())
            )
            if modules_path.exists() and work_empty:
                shutil.rmtree(modules_path)
                break

    @staticmethod
    def _set_submodule_ignore(git_root: Path, submodule_path: str) -> None:
        """在 .gitmodules 中为 submodule 设置 ignore = all"""
        gitmodules = git_root / ".gitmodules"
        if not gitmodules.exists():
            return
        lines = gitmodules.read_text(encoding="utf-8").splitlines(keepends=True)
        section_header = None
        for i, line in enumerate(lines):
            if line.strip().startswith("[submodule") and submodule_path in line:
                section_header = i
                break
        if section_header is None:
            return
        i = section_header + 1
        insert_pos = len(lines)
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith("["):
                insert_pos = i
                break
            if (
                stripped == "ignore"
                or stripped.startswith("ignore=")
                or stripped.startswith("ignore =")
            ):
                return  # 已存在
            i += 1
        indent = "\t"
        for j in range(section_header + 1, insert_pos):
            if lines[j].strip() and not lines[j].startswith("["):
                indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                break
        lines.insert(insert_pos, f"{indent}ignore = all\n")
        gitmodules.write_text("".join(lines), encoding="utf-8")


class ConfigManager:
    """配置管理器

    负责读写 driving.config.json，提供仓库配置的增删查改及路径辅助方法。
    配置文件路径为 {project_root}/driving.config.json。

    当项目根目录存在 driving.power.json 时，load() 自动切换为 Power 模式：
    合并所有 power 的配置后返回，写入操作仍需通过 PowerManager 路由到具体 power。
    """

    def __init__(self, project_root: Path):
        """初始化配置管理器

        Args:
            project_root: 项目根目录路径
        """
        self._project_root = project_root
        self._config_file = project_root / CONFIG_FILE_NAME
        # 内存中缓存的配置对象，None 表示尚未加载
        self._config: Optional[DrivingConfig] = None

    def _is_power_mode(self) -> bool:
        """判断当前是否为 Power 模式（项目根目录存在 driving.power.json）"""
        return (self._project_root / POWER_FILE_NAME).exists()

    # ==================== 核心读写方法 ====================

    def load(self) -> DrivingConfig:
        """加载配置文件

        - 传统模式：直接读取 driving.config.json，不存在则自动创建默认配置。
        - Power 模式：合并所有有效 power 的 driving.config.json 后返回。
          若所有 power 均无有效配置（driving.config.json 全部缺失），
          自动降级读取项目根目录的 driving.config.json。

        Returns:
            DrivingConfig: 配置对象

        Raises:
            ValueError: 配置文件格式非法或 power 冲突时抛出
        """
        # Power 模式：合并所有 power 配置
        if self._is_power_mode():
            pm = PowerManager(self._project_root)
            merged = pm.load_merged_config()
            if merged is not None:
                self._config = merged
                return merged
            # 所有 power 均无有效配置，降级读取根目录 driving.config.json
            # （fall through 到传统模式逻辑）

        # 传统模式
        if not self._config_file.exists():
            # 配置文件不存在，创建默认配置
            default_config = DrivingConfig(
                version=DEFAULT_VERSION,
                repos=[],
                default_commit_message=DEFAULT_COMMIT_MESSAGE,
                update_version_url=DEFAULT_UPDATE_VERSION_URL,
            )
            self.save(default_config)
            self._config = default_config
            return default_config

        # 读取并解析配置文件
        try:
            raw_text = self._config_file.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"配置文件读取失败：{e}") from e

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误：JSON 解析失败 — {e}") from e

        if not isinstance(data, dict):
            raise ValueError("配置文件格式错误：顶层结构必须为 JSON 对象")

        try:
            config = DrivingConfig.from_dict(data)
        except KeyError as e:
            raise ValueError(f"配置文件格式错误：缺少必填字段 {e}") from e
        except (TypeError, ValueError) as e:
            raise ValueError(f"配置文件格式错误：{e}") from e

        self._config = config
        return config

    def save(self, config: DrivingConfig) -> None:
        """将配置保存为格式化 JSON（仅传统模式可用）

        Power 模式下请通过 PowerManager.get_config_manager_for(name).save() 写入。

        Args:
            config: 要保存的配置对象
        """
        # 确保父目录存在
        self._config_file.parent.mkdir(parents=True, exist_ok=True)

        json_text = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        self._config_file.write_text(json_text, encoding="utf-8")
        self._config = config

    # ==================== 仓库增删查改 ====================

    def add_repo(self, repo: RepoConfig) -> None:
        """添加仓库到配置

        Args:
            repo: 要添加的仓库配置

        Raises:
            ValueError: 仓库名称已存在时抛出
        """
        config = self.load()

        # 检查名称是否重复
        if any(r.name == repo.name for r in config.repos):
            raise ValueError(f"仓库 '{repo.name}' 已存在，使用 --force 覆盖")

        config.repos.append(repo)
        self.save(config)

    def remove_repo(self, name: str) -> None:
        """从配置中删除仓库

        Args:
            name: 要删除的仓库名称

        Raises:
            ValueError: 仓库不存在时抛出
        """
        config = self.load()

        # 查找仓库
        original_count = len(config.repos)
        config.repos = [r for r in config.repos if r.name != name]

        if len(config.repos) == original_count:
            raise ValueError(f"仓库 '{name}' 不存在，使用 'driving repo list' 查看已安装仓库")

        self.save(config)

    def get_repo(self, name: str) -> Optional[RepoConfig]:
        """获取指定名称的仓库配置

        Args:
            name: 仓库名称

        Returns:
            RepoConfig: 仓库配置对象，不存在时返回 None
        """
        config = self.load()
        for repo in config.repos:
            if repo.name == name:
                return repo
        return None

    def get_all_repos(self) -> List[RepoConfig]:
        """获取所有仓库配置列表

        Returns:
            List[RepoConfig]: 所有仓库配置的列表
        """
        config = self.load()
        return list(config.repos)

    # ==================== 路径辅助方法 ====================

    def get_ai_driving_dir(self) -> Path:
        """返回 ai-driving/ 目录路径

        Returns:
            Path: ai-driving/ 目录的绝对路径
        """
        return self._project_root / AI_DRIVING_DIR_NAME

    def get_repo_dir(self, name: str) -> Path:
        """返回指定仓库的目录路径

        Args:
            name: 仓库名称

        Returns:
            Path: ai-driving/<name>/ 目录的绝对路径
        """
        return self.get_ai_driving_dir() / name

    def get_framework_base_dir(self, repo_name: str) -> Path:
        """返回指定仓库的框架安装目录路径

        Args:
            repo_name: 仓库名称

        Returns:
            Path: ai-driving/<repo_name>/submodules/ 目录的绝对路径
        """
        return self.get_repo_dir(repo_name) / "submodules"

    def get_all_gitlist_files(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 gitlist.json 文件路径列表

        只返回文件实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, gitlist_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            gitlist_path = self.get_repo_dir(repo.name) / "frameworks" / "gitlist.json"
            if gitlist_path.exists():
                result.append((repo.name, gitlist_path))
        return result

    def get_all_skills_dirs(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 skills/ 目录路径列表

        只返回目录实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, skills_dir_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            skills_dir = self.get_repo_dir(repo.name) / "skills"
            if skills_dir.exists():
                result.append((repo.name, skills_dir))
        return result

    def get_all_features_dirs(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 features/ 目录路径列表

        只返回目录实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, features_dir_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            features_dir = self.get_repo_dir(repo.name) / "features"
            if features_dir.exists():
                result.append((repo.name, features_dir))
        return result

    def get_all_rules_dirs(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 rules/ 目录路径列表

        只返回目录实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, rules_dir_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            rules_dir = self.get_repo_dir(repo.name) / "rules"
            if rules_dir.exists():
                result.append((repo.name, rules_dir))
        return result

    def get_all_agents_dirs(self) -> List[Tuple[str, Path]]:
        """返回所有仓库的 agents/ 目录路径列表

        只返回目录实际存在的条目。

        Returns:
            List[Tuple[str, Path]]: [(repo_name, agents_dir_path), ...] 列表
        """
        result = []
        for repo in self.get_all_repos():
            agents_dir = self.get_repo_dir(repo.name) / "agents"
            if agents_dir.exists():
                result.append((repo.name, agents_dir))
        return result

    def update_repo(self, repo: RepoConfig) -> None:
        """更新已存在仓库的配置

        Args:
            repo: 更新后的仓库配置

        Raises:
            ValueError: 仓库不存在时抛出
        """
        config = self.load()
        for i, r in enumerate(config.repos):
            if r.name == repo.name:
                config.repos[i] = repo
                self.save(config)
                return
        raise ValueError(f"仓库 '{repo.name}' 不存在")
