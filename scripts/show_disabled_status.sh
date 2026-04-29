#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="$ROOT_DIR/upstream"
STATE_PATH="${DISABLED_UPSTREAMS_PATH:-$ROOT_DIR/state/disabled-upstreams.yaml}"
AGENT_SKILLS_ROOT="$HOME/.agents/repos/agent-skills"
AGENT_SKILLS_MANIFEST="$AGENT_SKILLS_ROOT/manifest.yaml"

usage() {
  cat >&2 <<'EOF'
Usage:
  skill-status [--agent <agents|codex|claude|kimi|pi|hermes>]
  skill-status --upstream <upstream-id>
EOF
}

agent_filter=""
upstream_filter=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      agent_filter="${2:-}"
      shift 2
      ;;
    --upstream)
      upstream_filter="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

python3 - "$STATE_PATH" "$UPSTREAM_ROOT" "$AGENT_SKILLS_MANIFEST" "$AGENT_SKILLS_ROOT" "$ROOT_DIR" "$agent_filter" "$upstream_filter" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

import yaml

state_path = Path(sys.argv[1])
upstream_root = Path(sys.argv[2])
agent_skills_manifest = Path(sys.argv[3])
agent_skills_root = Path(sys.argv[4])
root_dir = sys.argv[5]
agent_filter = sys.argv[6]
upstream_filter = sys.argv[7]

RUNTIME_DIRS = {
    "agents": Path.home() / ".agents" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "kimi": Path.home() / ".kimi" / "skills",
    "pi": Path.home() / ".pi" / "agent" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
}

# ── agent-platform state ──────────────────────────────────

state = yaml.safe_load(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
disabled = state.get("disabled", {}) if isinstance(state, dict) else {}

global_disabled_upstreams = set(disabled.get("upstreams") or [])
global_disabled_skills = {}
for uid, skills in (disabled.get("skills") or {}).items():
    global_disabled_skills[uid] = set(skills or [])

agent_disabled = disabled.get("agents", {}) if isinstance(disabled, dict) else {}

# ── .disabled/ directory ──────────────────────────────────

disabled_dir = upstream_root / ".disabled"
physically_disabled_upstreams = set()
physically_disabled_skills = {}
if disabled_dir.exists():
    for item in disabled_dir.iterdir():
        if item.is_dir():
            physically_disabled_upstreams.add(item.name)
            for skill_dir in item.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                    physically_disabled_skills.setdefault(item.name, set()).add(skill_dir.name)

# ── Count skills per upstream ─────────────────────────────

def count_skills_in_upstream(upstream_id: str) -> int:
    for loc in [upstream_root, disabled_dir]:
        d = loc / upstream_id
        if d.is_dir():
            return len([s for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])
    return 0

# ── Render ────────────────────────────────────────────────

print()
print("=" * 60)
print("  禁用状态概览")
print("=" * 60)
print()

# ── Platform ──
print(f"[agent-platform]  {root_dir}")
print(f"  状态文件: {state_path}")
print()

if agent_filter:
    print(f"  (已过滤 agent: {agent_filter})")
    print()

# --- Global ---
print("  全局禁用:")
print()

if global_disabled_upstreams:
    print("    上游 (整体禁用):")
    for uid in sorted(global_disabled_upstreams):
        n = count_skills_in_upstream(uid)
        print(f"      - {uid}  ({n} skills)")
else:
    print("    上游 (整体禁用):  (无)")

print()

if global_disabled_skills:
    print("    单个 skill:")
    for uid in sorted(global_disabled_skills):
        skills = global_disabled_skills[uid]
        print(f"      {uid}:")
        for s in sorted(skills):
            print(f"        - {s}")
else:
    print("    单个 skill:  (无)")

print()

# --- Per-Agent ---
if agent_disabled:
    print("  Per-Agent 禁用:")
    print()
    for agent_id in sorted(agent_disabled):
        if agent_filter and agent_id != agent_filter:
            continue
        ad = agent_disabled[agent_id]
        au = set(ad.get("upstreams") or [])
        ask = {}
        for uid, skills in (ad.get("skills") or {}).items():
            ask[uid] = set(skills or [])

        parts = []
        for uid in sorted(au):
            parts.append(f"{uid} (整体)")
        for uid in sorted(ask):
            parts.append(f"{uid}/{', '.join(sorted(ask[uid]))}")
        print(f"    {agent_id}:  {', '.join(parts) if parts else '(无)'}")
    print()
else:
    print("  Per-Agent 禁用:  (无)")
    print()

# --- Per-Agent Whitelist ---
has_any_whitelist = False
if agent_disabled:
    for agent_id in sorted(agent_disabled):
        if agent_filter and agent_id != agent_filter:
            continue
        ae = agent_disabled[agent_id].get("enabled", {}) if isinstance(agent_disabled[agent_id], dict) else {}
        aeu = set(ae.get("upstreams") or [])
        aesk = {}
        for uid, skills in (ae.get("skills") or {}).items():
            aesk[uid] = set(skills or [])
        if aeu or aesk:
            if not has_any_whitelist:
                has_any_whitelist = True
                print("  Per-Agent 白名单 (覆盖全局禁用):")
                print()
            parts = []
            for uid in sorted(aeu):
                parts.append(f"{uid} (整体)")
            for uid in sorted(aesk):
                parts.append(f"{uid}/{', '.join(sorted(aesk[uid]))}")
            print(f"    {agent_id}:  {', '.join(parts)}")
    if has_any_whitelist:
        print()
else:
    pass  # no agent entries at all, no whitelist possible

# --- Physically disabled ---
if physically_disabled_upstreams:
    print("  物理禁用目录 (upstream/.disabled/):")
    for uid in sorted(physically_disabled_upstreams):
        skills = physically_disabled_skills.get(uid, set())
        print(f"    {uid}/  ({len(skills)} skills)")
        if skills:
            for s in sorted(skills):
                print(f"      - {s}")
    print()

# ── agent-skills state ────────────────────────────────────

print(f"[agent-skills]  {agent_skills_root}")
print(f"  manifest: {agent_skills_manifest}")
print()

if not agent_skills_manifest.exists():
    print("  (manifest 不存在)")
    print()
else:
    manifest = yaml.safe_load(agent_skills_manifest.read_text(encoding="utf-8"))
    skills_list = manifest.get("skills", []) if isinstance(manifest, dict) else []

    disabled_self = [s for s in skills_list if s.get("enabled") is False]

    if disabled_self:
        print("  已禁用 skills (manifest.yaml enabled: false):")
        print()
        for s in disabled_self:
            name = s.get("name", "?")
            desc = s.get("description", "")
            print(f"    - {name}")
            if desc:
                print(f"      {desc}")
        print()
    else:
        print("  已禁用 skills (manifest.yaml enabled: false):  (无)")
        print()

# ── Summary ────────────────────────────────────────────────

total_global_upstreams = len(global_disabled_upstreams)
total_global_skills = sum(len(skills) for skills in global_disabled_skills.values())
total_agent_disabled = sum(
    len(ad.get("upstreams") or []) + sum(len(skills or []) for skills in (ad.get("skills") or {}).values())
    for ad in agent_disabled.values()
)
total_self_disabled = len(disabled_self) if agent_skills_manifest.exists() else 0

print("-" * 60)
parts = []
if total_global_upstreams:
    parts.append(f"{total_global_upstreams} 个上游整体禁用")
if total_global_skills:
    parts.append(f"{total_global_skills} 个 skill 单独禁用")
if total_agent_disabled:
    parts.append(f"{total_agent_disabled} 个 per-agent 禁用项")
if total_self_disabled:
    parts.append(f"{total_self_disabled} 个自有 skill 禁用")
if not parts:
    parts.append("无禁用项")

print(f"  合计: {', '.join(parts)}")
print()
PY
