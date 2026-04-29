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
  skill-enable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] <upstream> <skill>
  skill-enable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] <upstream> --all
  skill-enable [--agent <agents|codex|claude|kimi|pi|hermes>] [--dry-run] agent <skill>
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

  python3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
import yaml

manifest_path = Path(sys.argv[1])
skill_name = sys.argv[2]
enable_all = sys.argv[3] == "true"

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
skills = manifest.get("skills", [])

if enable_all:
    affected = [s for s in skills if s.get("enabled") is False]
else:
    affected = [s for s in skills if s.get("name") == skill_name and s.get("enabled") is False]

if not affected:
    print("(无需操作: 目标 skill 已经是启用状态)")
    sys.exit(0)

print(f"\n  [agent-skills] 即将启用 {len(affected)} 个 skill:")
for s in affected:
    print(f"    - {s['name']}: {s.get('description', '')[:60]}")
print()
print(f"  将恢复 symlink 到: agents, claude, codex, kimi, pi, hermes (6 个 runtime)")
PY

  if [ "$dry_run" = "true" ]; then
    echo "  [dry-run] 以上为预览，未执行实际操作。"
    exit 0
  fi

  # Apply: modify manifest.yaml
  python3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
import yaml

manifest_path = Path(sys.argv[1])
skill_name = sys.argv[2]
enable_all = sys.argv[3] == "true"

manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
skills = manifest.get("skills", [])

for s in skills:
    if enable_all or s.get("name") == skill_name:
        s["enabled"] = True

manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"  [agent-skills] 已更新 manifest.yaml")
PY

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
enable_all = sys.argv[5] == "true"
agent_target = sys.argv[6]

def count_skills(d: Path) -> int:
    if not d.is_dir():
        return 0
    return len([s for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])

def list_skills(d: Path) -> list[str]:
    if not d.is_dir():
        return []
    return sorted([s.name for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])

source = disabled_root / upstream_id

if enable_all:
    affected = list_skills(source)
    label = f"上游 {upstream_id} (全部 {len(affected)} skills)"
else:
    affected = [skill_name] if (source / skill_name).is_dir() else []
    label = f"skill {upstream_id}/{skill_name}"

if not affected:
    if enable_all:
        # Check if upstream is in YAML but not in .disabled/
        print(f"  (上游 {upstream_id}: YAML 中有记录但 .disabled/ 中无内容 — 可能已手动恢复)")
    else:
        print(f"  (skill {upstream_id}/{skill_name} 不在 .disabled/ 中 — 无需启用)")
    sys.exit(0)

print(f"\n  [agent-platform] 即将启用: {label}")

rt_dir_map = {
    "agents": Path.home() / ".agents" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "kimi": Path.home() / ".kimi" / "skills",
    "pi": Path.home() / ".pi" / "agent" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
}

runtimes_affected = []
for rt_id, rt_dir in rt_dir_map.items():
    if agent_target and rt_id != agent_target:
        continue
    if rt_dir.is_dir():
        # Check which runtimes are missing these symlinks
        missing = 0
        for s in affected:
            link = rt_dir / s
            if not link.exists():
                missing += 1
        if missing > 0:
            runtimes_affected.append(f"{rt_id}(+{missing})")

if runtimes_affected:
    print(f"  将创建 symlinks 到: {', '.join(runtimes_affected)}")
else:
    print(f"  symlinks 已全部存在")
print()
PY

if [ "$dry_run" = "true" ]; then
  echo "  [dry-run] 以上为预览，未执行实际操作。"
  exit 0
fi

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
enable_all = sys.argv[6] == "true"
agent = sys.argv[7]

state = yaml.safe_load(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
if not isinstance(state, dict):
    state = {}
disabled = state.setdefault("disabled", {})

global_disabled_upstreams = disabled.get("upstreams") or []
global_disabled_skills = disabled.get("skills") or {}

if agent:
    disabled.setdefault("agents", {})
    agent_state = disabled["agents"].setdefault(agent, {})
    agent_state.setdefault("upstreams", [])
    agent_state.setdefault("skills", {})

    # ── Check if globally disabled → add to agent whitelist ──
    is_globally_disabled = (
        upstream in global_disabled_upstreams
        or (enable_all and upstream in global_disabled_upstreams)
    )
    if enable_all and upstream in global_disabled_upstreams:
        # Whole upstream globally disabled → whitelist entire upstream for this agent
        agent_enabled = agent_state.setdefault("enabled", {})
        agent_enabled.setdefault("upstreams", [])
        if upstream not in agent_enabled["upstreams"]:
            agent_enabled["upstreams"].append(upstream)
        # Also remove from agent disabled if present
        agent_state["upstreams"] = [u for u in agent_state["upstreams"] if u != upstream]

    elif upstream in global_disabled_upstreams:
        # Whole upstream globally disabled → whitelist this specific skill
        agent_enabled = agent_state.setdefault("enabled", {})
        agent_enabled.setdefault("skills", {})
        agent_enabled["skills"].setdefault(upstream, [])
        if skill not in agent_enabled["skills"][upstream]:
            agent_enabled["skills"][upstream].append(skill)

    elif skill and skill in global_disabled_skills.get(upstream, []):
        # Skill globally disabled → whitelist for this agent
        agent_enabled = agent_state.setdefault("enabled", {})
        agent_enabled.setdefault("skills", {})
        agent_enabled["skills"].setdefault(upstream, [])
        if skill not in agent_enabled["skills"][upstream]:
            agent_enabled["skills"][upstream].append(skill)
        # Also remove from agent disabled skills if present
        agent_state["skills"][upstream] = [
            s for s in agent_state["skills"].get(upstream, []) if s != skill
        ]
        if not agent_state["skills"][upstream]:
            agent_state["skills"].pop(upstream, None)

    else:
        # ── Not globally disabled: use per-agent disable state ──
        if enable_all:
            agent_state["upstreams"] = [u for u in agent_state["upstreams"] if u != upstream]
        else:
            agent_state["skills"][upstream] = [
                s for s in agent_state["skills"].get(upstream, []) if s != skill
            ]
            if not agent_state["skills"][upstream]:
                agent_state["skills"].pop(upstream, None)

        # Cleanup agent enabled whitelist if it was a re-enable of per-agent disable
        agent_enabled = agent_state.get("enabled", {})
        if enable_all and upstream in (agent_enabled.get("upstreams") or []):
            agent_enabled["upstreams"] = [u for u in agent_enabled["upstreams"] if u != upstream]
            if not agent_enabled["upstreams"]:
                agent_enabled.pop("upstreams", None)
        elif skill and skill in (agent_enabled.get("skills", {}).get(upstream, [])):
            agent_enabled["skills"][upstream] = [
                s for s in agent_enabled["skills"][upstream] if s != skill
            ]
            if not agent_enabled["skills"][upstream]:
                agent_enabled["skills"].pop(upstream, None)
            if not agent_enabled["skills"]:
                agent_enabled.pop("skills", None)
        if not agent_enabled:
            agent_state.pop("enabled", None)

else:
    # ── Global enable (no --agent): restore from .disabled/ ──
    target_upstream = upstream_root / upstream
    disabled_upstream = disabled_root / upstream

    if enable_all:
        global_disabled_upstreams[:] = [u for u in global_disabled_upstreams if u != upstream]
        if disabled_upstream.exists() and not target_upstream.exists():
            target_upstream.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(disabled_upstream), str(target_upstream))
    else:
        global_disabled_skills[upstream] = [
            s for s in global_disabled_skills.get(upstream, []) if s != skill
        ]
        if not global_disabled_skills.get(upstream):
            global_disabled_skills.pop(upstream, None)
        source = disabled_upstream / skill
        target = target_upstream / skill
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))

    disabled["upstreams"] = global_disabled_upstreams
    disabled["skills"] = global_disabled_skills

# Cleanup empty state keys
if agent:
    for key in list(agent_state.get("upstreams", [])):
        if not agent_state["upstreams"]:
            break
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

if state:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(yaml.safe_dump(state, sort_keys=True), encoding="utf-8")
elif state_path.exists():
    state_path.unlink()
PY

if [ -n "$agent" ]; then
  SKILL_AGENT_TARGETS="$agent" bash "$INSTALL_LINKS"
else
  SKILL_AGENT_TARGETS="all" bash "$INSTALL_LINKS"
fi
echo "  [agent-platform] 完成。"
