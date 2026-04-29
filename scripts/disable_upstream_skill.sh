#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="$ROOT_DIR/upstream"
DISABLED_ROOT="$UPSTREAM_ROOT/.disabled"
STATE_PATH="${DISABLED_UPSTREAMS_PATH:-$ROOT_DIR/state/disabled-upstreams.yaml}"
INSTALL_LINKS="$ROOT_DIR/scripts/install_links.sh"
AGENT_SKILLS_ROOT="$HOME/.agents/repos/agent-skills"
AGENT_SKILLS_MANIFEST="$AGENT_SKILLS_ROOT/manifest.yaml"

usage() {
  cat >&2 <<'EOF'
Usage:
  skill-disable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] <upstream> <skill>
  skill-disable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] <upstream> --all
  skill-disable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] agent <skill>
EOF
}

agent=""
upstream=""
skill=""
all="false"
dry_run="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      agent="${2:-}"
      shift 2
      ;;
    --upstream)
      upstream="${2:-}"
      shift 2
      ;;
    --skill)
      skill="${2:-}"
      shift 2
      ;;
    --all)
      all="true"
      shift
      ;;
    --dry-run)
      dry_run="true"
      shift
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

if [ -z "$upstream" ]; then
  usage
  exit 2
fi

if [ "$all" = "true" ] && [ -n "$skill" ]; then
  usage
  exit 2
fi

if [ "$all" != "true" ] && [ -z "$skill" ]; then
  usage
  exit 2
fi

case "$agent" in
  ""|agents|codex|claude|kimi|pi|hermes)
    ;;
  *)
    usage
    exit 2
    ;;
esac

# ── agent-skills upstream: special handling ─────────────────
if [ "$upstream" = "agent-skills" ]; then
  if [ ! -f "$AGENT_SKILLS_MANIFEST" ]; then
    echo "[!] agent-skills manifest not found: $AGENT_SKILLS_MANIFEST" >&2
    exit 1
  fi

  # Impact analysis (shared by dry-run and real execution)
  python3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
import yaml

manifest_path = Path(sys.argv[1])
skill_name = sys.argv[2]
disable_all = sys.argv[3] == "true"

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
skills = manifest.get("skills", [])

if disable_all:
    affected = [s for s in skills if s.get("enabled") is not False]
else:
    affected = [s for s in skills if s.get("name") == skill_name and s.get("enabled") is not False]

if not affected:
    print("(无需操作: 目标 skill 已经处于禁用状态)")
    sys.exit(0)

print(f"\n  [agent-skills] 即将禁用 {len(affected)} 个 skill:")
for s in affected:
    print(f"    - {s['name']}: {s.get('description', '')[:60]}")
print()
print(f"  受影响 runtime: agents, claude, codex, kimi, pi, hermes (6 个)")
PY

  if [ "$dry_run" = "true" ]; then
    echo "  [dry-run] 以上为预览，未执行实际操作。"
    exit 0
  fi

  echo "  继续? [y/N]"
  read -r confirm
  case "$confirm" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "  已取消。"; exit 0 ;;
  esac

  # Apply: modify manifest.yaml
  python3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
import yaml

manifest_path = Path(sys.argv[1])
skill_name = sys.argv[2]
disable_all = sys.argv[3] == "true"

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
skills = manifest.get("skills", [])

for s in skills:
    if disable_all or s.get("name") == skill_name:
        s["enabled"] = False

manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"  [agent-skills] 已更新 manifest.yaml")
PY

  # Re-install agent-skills to apply symlink changes
  if [ -f "$AGENT_SKILLS_ROOT/scripts/install.mjs" ]; then
    node "$AGENT_SKILLS_ROOT/scripts/install.mjs" 2>&1 | tail -3
  fi
  echo "  [agent-skills] 完成。"
  exit 0
fi

# ── Standard upstream: agent-platform ──────────────────────

# Impact analysis
python3 - "$UPSTREAM_ROOT" "$DISABLED_ROOT" "$upstream" "$skill" "$all" "$agent" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path

upstream_root = Path(sys.argv[1])
disabled_root = Path(sys.argv[2])
upstream_id = sys.argv[3]
skill_name = sys.argv[4]
disable_all = sys.argv[5] == "true"
agent_target = sys.argv[6]

RUNTIME_LABELS = {
    "agents": "~/.agents/skills",
    "claude": "~/.claude/skills",
    "codex": "~/.codex/skills",
    "kimi": "~/.kimi/skills",
    "pi": "~/.pi/agent/skills",
    "hermes": "~/.hermes/skills",
}

def count_skills(d: Path) -> int:
    if not d.is_dir():
        return 0
    return len([s for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])

def list_skills(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted([s.name for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])

source = upstream_root / upstream_id
disabled = disabled_root / upstream_id

# ── Check for per-agent whitelist override ──
has_agent_whitelist = False
if agent_target:
    state_data = {}
    disabled_path = upstream_root.parent / "state" / "disabled-upstreams.yaml"
    if disabled_path.exists():
        import yaml as _yaml
        _state_raw = _yaml.safe_load(disabled_path.read_text(encoding="utf-8"))
        state_data = _state_raw.get("disabled", {}) if isinstance(_state_raw, dict) else {}
    agent_sd = (state_data.get("agents") or {}).get(agent_target, {})
    agent_enabled = agent_sd.get("enabled", {}) if isinstance(agent_sd, dict) else {}
    if disable_all:
        has_agent_whitelist = upstream_id in (agent_enabled.get("upstreams") or [])
    else:
        has_agent_whitelist = skill_name in (agent_enabled.get("skills") or {}).get(upstream_id, [])

if disable_all:
    affected = list_skills(source)
    label = f"上游 {upstream_id} (全部 {len(affected)} skills)"
else:
    affected = [skill_name] if (source / skill_name).is_dir() else []
    label = f"skill {upstream_id}/{skill_name}"

if not affected:
    source2 = disabled_root / upstream_id
    if has_agent_whitelist:
        if disable_all:
            print(f"\n  [agent-platform] 即将移除 {upstream_id} 的 {agent_target} 白名单覆盖")
            print(f"  上游 {upstream_id} 保持全局禁用，{agent_target} 白名单移除后该 agent 将不再可见。")
        else:
            print(f"\n  [agent-platform] 即将移除 {upstream_id}/{skill_name} 的 {agent_target} 白名单覆盖")
            print(f"  skill {upstream_id}/{skill_name} 保持全局禁用，{agent_target} 白名单移除后该 agent 将不再可见。")
        sys.exit(0)
    if disable_all:
        affected2 = list_skills(source2)
        if affected2:
            print(f"  (上游 {upstream_id} 已在 .disabled/ 中，共 {len(affected2)} skills)")
        else:
            print(f"  (上游 {upstream_id} 不存在或已全部禁用)")
    else:
        if (source2 / skill_name).is_dir():
            print(f"  (skill {upstream_id}/{skill_name} 已在 .disabled/ 中)")
        else:
            print(f"  (skill {upstream_id}/{skill_name} 不存在或已禁用)")
    sys.exit(0)

print(f"\n  [agent-platform] 即将禁用: {label}")

# Check symlink status in each runtime
runtimes_affected = []
for rt_id, rt_path in RUNTIME_LABELS.items():
    if agent_target and rt_id != agent_target:
        continue
    rt_dir = Path.home() / rt_path.replace("~/.", ".", 1).replace("~", str(Path.home()))
    # Map back - simpler approach:
    pass

# Count potential symlink impact
rt_dir_map = {
    "agents": Path.home() / ".agents" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "kimi": Path.home() / ".kimi" / "skills",
    "pi": Path.home() / ".pi" / "agent" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
}

for rt_id, rt_dir in rt_dir_map.items():
    if agent_target and rt_id != agent_target:
        continue
    if rt_dir.is_dir():
        linked = 0
        for s in affected:
            link = rt_dir / s
            if link.is_symlink():
                linked += 1
        if linked > 0:
            runtimes_affected.append(f"{rt_id}({linked})")

if runtimes_affected:
    print(f"  受影响 runtime: {', '.join(runtimes_affected)}")
    print(f"  将移除 symlinks: ~{sum(int(x.split('(')[1].rstrip(')')) for x in runtimes_affected)} 个")
else:
    print(f"  受影响 runtime: (无现有 symlink)")
print()
PY

if [ "$dry_run" = "true" ]; then
  echo "  [dry-run] 以上为预览，未执行实际操作。"
  exit 0
fi

echo "  继续? [y/N]"
read -r confirm
case "$confirm" in
  [yY]|[yY][eE][sS]) ;;
  *) echo "  已取消。"; exit 0 ;;
esac

# Execute: update YAML state and move directories
python3 - "$STATE_PATH" "$UPSTREAM_ROOT" "$DISABLED_ROOT" "$upstream" "$skill" "$all" "$agent" <<'PY'
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

state_path = Path(sys.argv[1])
upstream_root = Path(sys.argv[2])
disabled_root = Path(sys.argv[3])
upstream = sys.argv[4]
skill = sys.argv[5]
disable_all = sys.argv[6] == "true"
agent = sys.argv[7]

state = yaml.safe_load(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
if not isinstance(state, dict):
    state = {}
disabled = state.setdefault("disabled", {})

global_disabled_upstreams = disabled.get("upstreams") or []

if agent:
    disabled.setdefault("agents", {})
    agent_state = disabled["agents"].setdefault(agent, {})
    agent_state.setdefault("upstreams", [])
    agent_state.setdefault("skills", {})

    # ── Check for whitelist override first ──
    agent_enabled = agent_state.get("enabled", {})
    agent_enabled_upstreams = agent_enabled.get("upstreams") or []
    agent_enabled_skills = agent_enabled.get("skills", {}).get(upstream, [])

    if disable_all and upstream in agent_enabled_upstreams:
        # Remove whitelist override → falls back to globally disabled
        agent_enabled["upstreams"] = [u for u in agent_enabled_upstreams if u != upstream]
        if not agent_enabled["upstreams"]:
            agent_enabled.pop("upstreams", None)
        if not agent_enabled:
            agent_state.pop("enabled", None)

    elif skill and skill in agent_enabled_skills:
        # Remove whitelist override → falls back to globally disabled
        agent_enabled["skills"][upstream] = [s for s in agent_enabled_skills if s != skill]
        if not agent_enabled["skills"][upstream]:
            agent_enabled["skills"].pop(upstream, None)
            if not agent_enabled["skills"]:
                agent_enabled.pop("skills", None)
        if not agent_enabled:
            agent_state.pop("enabled", None)

    else:
        # ── Not a whitelist removal: add to per-agent disabled ──
        if disable_all:
            if upstream not in agent_state["upstreams"]:
                agent_state["upstreams"].append(upstream)
        else:
            if skill not in agent_state["skills"].get(upstream, []):
                agent_state["skills"].setdefault(upstream, []).append(skill)

else:
    # ── Global disable: move to .disabled/ ──
    source_upstream = upstream_root / upstream
    target_upstream = disabled_root / upstream

    if disable_all:
        upstreams = disabled.setdefault("upstreams", [])
        if upstream not in upstreams:
            upstreams.append(upstream)
        if source_upstream.exists():
            target_upstream.parent.mkdir(parents=True, exist_ok=True)
            if target_upstream.exists():
                shutil.rmtree(target_upstream)
            shutil.move(str(source_upstream), str(target_upstream))
    else:
        skills = disabled.setdefault("skills", {}).setdefault(upstream, [])
        if skill not in skills:
            skills.append(skill)
        source = source_upstream / skill
        target = target_upstream / skill
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))

# Cleanup empty state keys
if agent:
    if "upstreams" in agent_state and not agent_state["upstreams"]:
        agent_state.pop("upstreams", None)
    if "skills" in agent_state and not agent_state["skills"]:
        agent_state.pop("skills", None)
    if "enabled" in agent_state:
        ae = agent_state["enabled"]
        if "upstreams" in ae and not ae["upstreams"]:
            ae.pop("upstreams", None)
        if "skills" in ae and not ae["skills"]:
            ae.pop("skills", None)
        if not ae:
            agent_state.pop("enabled", None)
    if not agent_state:
        disabled["agents"].pop(agent, None)
if not disabled.get("agents"):
    disabled.pop("agents", None)
if not disabled.get("upstreams"):
    disabled.pop("upstreams", None)
if not disabled.get("skills"):
    disabled.pop("skills", None)
if not disabled:
    state.pop("disabled", None)

state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(yaml.safe_dump(state, sort_keys=True), encoding="utf-8")
PY

if [ -n "$agent" ]; then
  SKILL_AGENT_TARGETS="$agent" bash "$INSTALL_LINKS"
else
  SKILL_AGENT_TARGETS="all" bash "$INSTALL_LINKS"
fi
echo "  [agent-platform] 完成。"
