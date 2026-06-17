#!/usr/bin/env bash
# skill-status — show disabled upstream skills (global only)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_PATH="${DISABLED_UPSTREAMS_PATH:-$ROOT_DIR/state/disabled-upstreams.yaml}"

PYTHON3="$(command -v python3)"
"$PYTHON3" -c "import yaml" 2>/dev/null || PYTHON3="/home/lkshpc/anaconda3/bin/python3"

upstream_filter=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --upstream) upstream_filter="${2:-}"; shift 2 ;;
    -h|--help)  echo "Usage: skill-status [--upstream <id>]"; exit 0 ;;
    *)          echo "Unknown: $1" >&2; exit 2 ;;
  esac
done

$PYTHON3 - "$STATE_PATH" "$ROOT_DIR" "$upstream_filter" <<'PY'
import sys
from pathlib import Path
import yaml

state_path = Path(sys.argv[1]); root_dir = sys.argv[2]; upstream_filter = sys.argv[3]
upstream_root = Path(root_dir) / "upstream"
disabled_dir = upstream_root / ".disabled"
manifest_path = Path.home() / ".agents" / "repos" / "agent-skills" / "manifest.yaml"

state = yaml.safe_load(state_path.read_text(encoding="utf-8")) if state_path.exists() else {} or {}
disabled = state.get("disabled", {})

global_disabled_upstreams = set(disabled.get("upstreams") or [])
global_disabled_skills = {}
for uid, skills in (disabled.get("skills") or {}).items():
    global_disabled_skills[uid] = set(skills or [])

# Physical .disabled/
physically_disabled_upstreams = set()
physically_disabled_skills = {}
if disabled_dir.exists():
    for item in disabled_dir.iterdir():
        if item.is_dir():
            physically_disabled_upstreams.add(item.name)
            for skill_dir in item.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                    physically_disabled_skills.setdefault(item.name, set()).add(skill_dir.name)

def count_skills(uid):
    for loc in [upstream_root, disabled_dir]:
        d = loc / uid
        if d.is_dir():
            return len([s for s in d.iterdir() if s.is_dir() and (s / "SKILL.md").is_file()])
    return 0

print(); print("=" * 60); print("  禁用状态概览"); print("=" * 60); print()
print(f"[agent-platform]  {root_dir}"); print(f"  状态文件: {state_path}"); print()

if upstream_filter:
    print(f"  (过滤: {upstream_filter})"); print()

print("  全局禁用:"); print()
if global_disabled_upstreams:
    print("    上游 (整体禁用):")
    for uid in sorted(global_disabled_upstreams):
        if upstream_filter and uid != upstream_filter: continue
        print(f"      - {uid}  ({count_skills(uid)} skills)")
else:
    print("    上游 (整体禁用):  (无)")
print()
if global_disabled_skills:
    print("    单个 skill:")
    for uid in sorted(global_disabled_skills):
        if upstream_filter and uid != upstream_filter: continue
        skills = global_disabled_skills[uid]
        print(f"      {uid}:")
        for s in sorted(skills): print(f"        - {s}")
else:
    print("    单个 skill:  (无)")
print()

if physically_disabled_upstreams:
    print("  物理禁用目录 (upstream/.disabled/):")
    for uid in sorted(physically_disabled_upstreams):
        skills = physically_disabled_skills.get(uid, set())
        print(f"    {uid}/  ({len(skills)} skills)")
        for s in sorted(skills): print(f"      - {s}")
    print()

# agent-skills
print(f"[agent-skills]  ~/.agents/repos/agent-skills")
if manifest_path.exists():
    m = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    ds = [s for s in m.get("skills", []) if s.get("enabled") is False]
    if ds:
        print("  已禁用 skills (manifest.yaml enabled: false):")
        for s in ds: print(f"    - {s.get('name', '?')}")
    else:
        print("  已禁用 skills:  (无)")
else:
    print("  (manifest 不存在)")
print()

t_u = len(global_disabled_upstreams); t_s = sum(len(v) for v in global_disabled_skills.values())
print("-" * 60)
parts = []
if t_u: parts.append(f"{t_u} 个上游整体禁用")
if t_s: parts.append(f"{t_s} 个 skill 单独禁用")
if ds: parts.append(f"{len(ds)} 个自有 skill 禁用")
print(f"  合计: {', '.join(parts) if parts else '无禁用项'}")
print()
PY
