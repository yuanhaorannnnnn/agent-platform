#!/usr/bin/env bash
# toggle_upstream_skill.sh — enable/disable upstream skills (global only)
# Usage:
#   skill-toggle --disable <upstream> <skill|--all>
#   skill-toggle --enable  <upstream> <skill|--all>
#   skill-toggle --disable agent-skills <skill|--all>
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="$ROOT_DIR/upstream"
DISABLED_ROOT="$UPSTREAM_ROOT/.disabled"
STATE_PATH="${DISABLED_UPSTREAMS_PATH:-$ROOT_DIR/state/disabled-upstreams.yaml}"
AGENT_SKILLS_MANIFEST="$HOME/.agents/repos/agent-skills/manifest.yaml"

PYTHON3="$(command -v python3)"
"$PYTHON3" -c "import yaml" 2>/dev/null || PYTHON3="/home/lkshpc/anaconda3/bin/python3"

usage() { cat >&2 <<'EOF'
Usage: skill-toggle --disable|--enable <upstream> <skill|--all> [--dry-run]
EOF
}

action="" upstream="" skill="" all=false dry_run=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --disable) action="disable"; shift ;;
    --enable)  action="enable"; shift ;;
    --dry-run) dry_run=true; shift ;;
    --all)     all=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      [ -z "$upstream" ] && { upstream="$1"; shift; continue; }
      [ -z "$skill" ]    && { skill="$1"; shift; continue; }
      usage; exit 2 ;;
  esac
done

[ -z "$action" ] || [ -z "$upstream" ] && { usage; exit 2; }
{ [ "$all" = "true" ] && [ -n "$skill" ]; } || { [ "$all" != "true" ] && [ -z "$skill" ]; } && { usage; exit 2; }

# ── agent-skills: handle via manifest.yaml ──────────────────────────
if [ "$upstream" = "agent-skills" ]; then
  [ ! -f "$AGENT_SKILLS_MANIFEST" ] && { echo "[!] agent-skills manifest not found" >&2; exit 1; }

  $PYTHON3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" "$action" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1]); skill_name = sys.argv[2]
all_skills = sys.argv[3] == "true"
enable = sys.argv[4] == "enable"

m = yaml.safe_load(path.read_text(encoding="utf-8"))
skills = m.get("skills", [])
targets = skills if all_skills else [s for s in skills if s.get("name") == skill_name]
if not targets:
    print(f"(no matching skills)"); sys.exit(0)

print(f"\n  [agent-skills] {'启用' if enable else '禁用'} {len(targets)} 个 skill:")
for s in targets:
    print(f"    - {s['name']}: {s.get('description', '')[:60]}")
PY
  if [ "$dry_run" = "true" ]; then
    echo "  [dry-run] 预览，未执行。"; exit 0
  fi

  echo "  继续? [y/N]"
  read -r confirm
  case "$confirm" in [yY]|[yY][eE][sS]) ;; *) echo "已取消。"; exit 0 ;; esac

  $PYTHON3 - "$AGENT_SKILLS_MANIFEST" "$skill" "$all" "$action" <<'PY'
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1]); skill_name = sys.argv[2]
all_skills = sys.argv[3] == "true"; enable = sys.argv[4] == "enable"

m = yaml.safe_load(path.read_text(encoding="utf-8"))
for s in m.get("skills", []):
    if all_skills or s.get("name") == skill_name:
        s["enabled"] = enable
path.write_text(yaml.safe_dump(m, sort_keys=False, allow_unicode=True), encoding="utf-8")
print(f"  [agent-skills] manifest.yaml 已更新")
PY

  [ -f "$HOME/.agents/repos/agent-skills/scripts/install.mjs" ] && node "$HOME/.agents/repos/agent-skills/scripts/install.mjs" 2>&1 | tail -3
  echo "  [agent-skills] 完成。"; exit 0
fi

# ── Standard upstream: move to/from .disabled/ ──────────────────────
SRC="$UPSTREAM_ROOT/$upstream"
DST="$DISABLED_ROOT/$upstream"

if [ "$all" = "true" ]; then
  [ "$action" = "disable" ] && { from="$SRC"; to="$DST"; } || { from="$DST"; to="$SRC"; }
  label="上游 $upstream (全部)"
else
  [ "$action" = "disable" ] && { from="$SRC/$skill"; to="$DST/$skill"; } || { from="$DST/$skill"; to="$SRC/$skill"; }
  label="skill $upstream/$skill"
fi

if [ ! -e "$from" ]; then
  echo "  $from 不存在，无需操作。"; exit 0
fi

echo "  [$action] $label"
echo "    从: $from"
echo "    到: $to"

if [ "$dry_run" = "true" ]; then
  echo "  [dry-run] 预览，未执行。"; exit 0
fi

echo "  继续? [y/N]"
read -r confirm
case "$confirm" in [yY]|[yY][eE][sS]) ;; *) echo "已取消。"; exit 0 ;; esac

mkdir -p "$(dirname "$to")"
[ -e "$to" ] && rm -rf "$to"
mv "$from" "$to"

# Update YAML state
$PYTHON3 - "$STATE_PATH" "$upstream" "$skill" "$all" "$action" <<'PY'
import sys
from pathlib import Path
import yaml

state_path = Path(sys.argv[1]); upstream = sys.argv[2]
skill = sys.argv[3]; all_skills = sys.argv[4] == "true"; enable = sys.argv[5] == "enable"

s = yaml.safe_load(state_path.read_text(encoding="utf-8")) if state_path.exists() else {} or {}
d = s.setdefault("disabled", {})

if all_skills:
    lst = d.setdefault("upstreams", [])
    if enable and upstream in lst: lst.remove(upstream)
    if not enable and upstream not in lst: lst.append(upstream)
else:
    lst = d.setdefault("skills", {}).setdefault(upstream, [])
    if enable and skill in lst: lst.remove(skill)
    if not enable and skill not in lst: lst.append(skill)

# Clean empty
for k in ("upstreams", "skills"):
    if k in d and not d[k]: del d[k]
if not d: s.pop("disabled", None)

state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(yaml.safe_dump(s, sort_keys=True), encoding="utf-8")
PY

bash "$ROOT_DIR/scripts/install_links.sh"
echo "  完成。"
