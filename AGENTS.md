# Repo Agent Index

这个仓库的本地 agent 系统入口索引。

## Routing Table

- 会话保存 / 恢复 / conversation 身份规则：
  读取 `~/.agents/skills/save-conversation/SKILL.md` 和 `~/.agents/skills/restore-conversation/SKILL.md`
- 当前任务的 planning 文档与默认写入路径：
  `.planning/conversations/<conversation-id>/`
- 项目级长期记忆与架构背景：
  `.agent-state/MEMORY.md`
- 可复用错误模式与长期防错规则：
  `.agent-state/rules/mistakes.md`
- 当前对话压缩状态：
  `.agent-state/conversations/<conversation>.md`
- 全局用户偏好和跨仓库风格：
  `~/.codex/AGENTS.md`

## What Not To Put Here

- 不要把完整 skill 工作流复制到这里。
- 不要把 conversation 运行态内容复制到这里。
- 不要把当前任务 planning 文档重新散落到仓库根目录。
- 不要把所有历史错误原样堆到这里。
- 不要把 planning 模板正文复制到这里。

保持这个文件小而稳定，让它始终只做目录和入口。

<!-- BEGIN AGENT-SYSTEM -->
## Repo Agent System

### Conversation Save/Restore

- Active conversation pointer: `.agent-state/ACTIVE_CONVERSATION`
- Conversation summaries: `.agent-state/conversations/<conversation>.md`
- Conversation files should focus on conversation context, current goals, todos,
  and risks — not git state snapshots.
- Use conversation id as the primary key, not branch name.
- To create an independent new session, always specify a session name explicitly;
  do not rely on ACTIVE_CONVERSATION fallback.

### Planning

- Task planning files: `.planning/conversations/<conversation-id>/`
  - `spec.md`, `task_plan.md`, `findings.md`, `progress.md`
- Planning id can be a conversation id or a stable workflow name (e.g. `rpm_limit`).
- Do not keep planning files long-term in the repo root; migrate old files to the
  path above before continuing to maintain them.

### Source Of Truth Map

- Repo runtime memory + architecture: `.agent-state/MEMORY.md`
- Guardrails (durable + runtime): `.agent-state/rules/mistakes.md`
- Conversation recap: `.agent-state/conversations/<conversation>.md`
- Task planning: `.planning/conversations/<conversation-id>/`
- Personal skills source repo: `~/.agents/repos/agent-skills`
- Runtime skill surface: `~/.agents/skills`
<!-- END AGENT-SYSTEM -->
