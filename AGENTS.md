# Agent Platform

多层 skill 管理平台。自有 skill 在 `~/.agents/repos/agent-skills/`，不在此管理。

## 架构

三层协作模型：

1. **Manifest** — source of truth。`migration/upstream-manifest.yaml` 声明上游仓库和 tracked skills
2. **策略层** — `state/disabled-upstreams.yaml` 控制全局/每 agent 的启用禁用，支持 per-agent whitelist 覆盖
3. **运行时** — `scripts/install_links.sh` 将上游快照 symlink 到 `~/.agents/skills` / `~/.claude/skills`

```
manifest.yaml → sync_all_upstreams.py → upstream/ (快照)
                                              ↓
disabled-upstreams.yaml → install_links.sh → ~/.agents/skills
                                              → ~/.claude/skills
```
