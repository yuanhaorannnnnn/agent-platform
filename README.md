# Agent Platform

本地多 agent skill 管理平台。负责第三方上游 skill 仓库的快照、同步、运行时链接和禁用/启用状态管理。

与 [`agent-skills`](https://github.com/yuanhaorannnnnn/agent-skills) 的关系：

| 仓库 | 职责 | 内容 |
|------|------|------|
| `agent-skills` | 自有 skill 产品 | 自研 skill（save/restore conversation、work-report、video-ingest 等） |
| `agent-platform` | 第三方 skill 管理 | 上游快照、runtime symlink、disable/enable 状态 |

## 目录结构

```
.
├── scripts/          # 管理脚本
│   ├── disable_upstream_skill.sh   # skill-disable / skill-dis
│   ├── enable_upstream_skill.sh    # skill-enable / skill-en
│   ├── show_disabled_status.sh     # skill-status / skill-disabled
│   ├── install_links.sh            # 创建 runtime symlink
│   ├── sync_upstream_skills.py     # 同步单个上游
│   ├── sync_all_upstreams.py       # 批量同步所有上游
│   └── install_upstream_sync_timer.sh
├── tests/            # 测试
│   └── test_sync_upstream_skills.py
├── migration/        # 迁移配置
│   └── upstream-manifest.yaml      # 上游清单与 curated skill 追踪
├── AGENTS.md         # Repo-local agent 系统索引
└── CLAUDE.md         # 项目指引
```

## 支持的 Runtime

skill 通过 symlink 分发到以下 agent runtime 目录：

| Agent | Runtime 目录 |
|-------|-------------|
| agents | `~/.agents/skills` |
| claude | `~/.claude/skills` |
| codex | `~/.codex/skills` |
| kimi | `~/.kimi/skills` |
| pi | `~/.pi/agent/skills` |
| hermes | `~/.hermes/skills` |

## 使用

```bash
# 查看禁用状态
skill-status
skill-status --agent claude

# 禁用/启用上游 skill（全局或 per-agent）
skill-disable [--agent <agent>] <upstream> <skill>
skill-enable [--agent <agent>] <upstream> <skill>

# 同步上游快照
python3 scripts/sync_upstream_skills.py --upstream-id anthropics-skills
```

## 状态文件

- `state/disabled-upstreams.yaml` — 全局和 per-agent 禁用状态（运行时生成，不 track）
- `upstream/` — 第三方上游快照（运行时同步，不 track）
- `upstream/.disabled/` — 物理禁用目录
