# Changelog

All notable changes to Driving CLI Tool will be documented in this file.

## [1.0.0] 2026-01-26

- cli tool独立维护

### 架构特点

- 使用 Git submodule 管理 driving 配置
- 框架仓库存储在项目的 `.driving/submodules/` 中
- 所有内容可被 Git 追踪和版本控制
- IDE 友好，可正确识别和索引
- 支持团队协作和版本一致性

### 项目结构

```
cli-tool/
├── driving/              # 主包
│   ├── cli.py           # CLI 入口
│   ├── commands/        # 命令实现
│   │   ├── repo.py      # Driving 配置管理
│   │   ├── link.py      # Submodule 管理
│   │   └── framework.py # 框架仓库管理
│   ├── utils/           # 工具函数
│   │   ├── config.py    # 配置
│   │   ├── logger.py    # 日志
│   │   └── git_helper.py # Git 操作
│   └── models/          # 数据模型
│       └── framework.py # 框架模型
├── tests/               # 测试目录
├── pyproject.toml       # 安装配置
├── requirements.txt     # 依赖列表
└── README.md            # 项目说明
```

#### 文档

- `README.md` - 项目概述和安装说明
- `QUICKSTART.md` - 快速开始指南
