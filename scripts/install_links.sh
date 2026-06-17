#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="$ROOT_DIR/upstream"
MANIFEST_PATH="$ROOT_DIR/migration/upstream-manifest.yaml"
DISABLED_UPSTREAMS_PATH="${DISABLED_UPSTREAMS_PATH:-$ROOT_DIR/state/disabled-upstreams.yaml}"
SKILL_AGENT_TARGETS="${SKILL_AGENT_TARGETS:-all}"

target_dir_for_agent() {
  case "$1" in
    agents)
      printf '%s\n' "$HOME/.agents/skills"
      ;;
    claude)
      printf '%s\n' "$HOME/.claude/skills"
      ;;
    *)
      return 1
      ;;
  esac
}

expand_agent_targets() {
  printf '%s\n' "$SKILL_AGENT_TARGETS" | tr ', ' '\n' | sed '/^$/d' | while IFS= read -r target; do
    case "$target" in
      all)
        printf '%s\n' agents claude
        ;;
      agents|claude)
        printf '%s\n' "$target"
        ;;
      *)
        echo "Unknown skill agent target: $target" >&2
        exit 2
        ;;
    esac
  done | sort -u
}

EXPANDED_AGENT_TARGETS="$(expand_agent_targets | tr '\n' ' ')"

target_selected() {
  case " $EXPANDED_AGENT_TARGETS " in
    *" $1 "*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

collect_skill_targets() {
  python3 - "$1" "$2" "$3" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path
import yaml

upstream_root = Path(sys.argv[1])
disabled_path = Path(sys.argv[2])
manifest_path = Path(sys.argv[3])

disabled_data = yaml.safe_load(disabled_path.read_text(encoding="utf-8")) if disabled_path.exists() else {}
disabled = disabled_data.get("disabled", {}) if isinstance(disabled_data, dict) else {}
disabled_upstreams = set(disabled.get("upstreams") or [])
disabled_skills = {uid: set(skills or []) for uid, skills in (disabled.get("skills") or {}).items()}

manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
curated_upstreams = {}
for upstream in manifest_data.get("upstreams", []):
    uid = upstream["id"]
    if upstream.get("runtime_link_mode") == "curated":
        curated_upstreams[uid] = {s["name"] for s in upstream.get("tracked_skills", [])}

def should_skip(uid, skill):
    if uid in disabled_upstreams:
        return True
    return skill in disabled_skills.get(uid, set())

def scan_skills(scan_root):
    if not scan_root.exists():
        return
    for upstream_dir in sorted(scan_root.iterdir()):
        if not upstream_dir.is_dir():
            continue
        upstream_id = upstream_dir.name
        is_curated = upstream_id in curated_upstreams
        for skill_dir in sorted(upstream_dir.iterdir()):
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            if should_skip(upstream_id, skill_dir.name):
                continue
            if is_curated and skill_dir.name not in curated_upstreams[upstream_id]:
                continue
            print(f"{skill_dir.name}\t{skill_dir}")

scan_skills(upstream_root)
PY
}

mkdir -p "$HOME/.claude" "$HOME/.agents"

if target_selected agents || target_selected claude; then
if [ -d "$HOME/.claude/agents" ]; then
  if [ -L "$HOME/.claude/agents/repo-agents" ]; then
    existing_target="$(readlink "$HOME/.claude/agents/repo-agents" || true)"
    case "$existing_target" in
      "$ROOT_DIR/"*)
        rm -f "$HOME/.claude/agents/repo-agents"
        ;;
    esac
  fi
fi
fi

if target_selected agents || target_selected claude; then
if [ -d "$HOME/.claude/commands" ]; then
  if [ -L "$HOME/.claude/commands/repo-commands" ]; then
    existing_target="$(readlink "$HOME/.claude/commands/repo-commands" || true)"
    case "$existing_target" in
      "$ROOT_DIR/"*)
        rm -f "$HOME/.claude/commands/repo-commands"
        ;;
    esac
  fi
fi
fi

if target_selected agents || target_selected claude; then
if [ -d "$HOME/.claude/skills" ]; then
  while IFS= read -r existing_link; do
    existing_target="$(readlink "$existing_link" || true)"
    case "$existing_target" in
      "$ROOT_DIR/"*|"$UPSTREAM_ROOT/"*)
        rm -f "$existing_link"
        ;;
    esac
  done < <(find "$HOME/.claude/skills" -type l)
fi
fi

for agent_target in $EXPANDED_AGENT_TARGETS; do
  target_dir="$(target_dir_for_agent "$agent_target")"
  mkdir -p "$target_dir"

  for existing_link in "$target_dir"/*; do
    [ -L "$existing_link" ] || continue
    existing_target="$(readlink "$existing_link" || true)"
    case "$existing_target" in
      "$ROOT_DIR/"*|"$UPSTREAM_ROOT/"*)
        rm -f "$existing_link"
        ;;
    esac
  done

  while IFS=$'\t' read -r skill_name target; do
    [ -n "$skill_name" ] || continue
    [ -n "$target" ] || continue
    ln -sfn "$target" "$target_dir/$skill_name"
  done < <(collect_skill_targets "$UPSTREAM_ROOT" "$DISABLED_UPSTREAMS_PATH" "$MANIFEST_PATH" | sort -u)

  echo "Linked repo-managed assets into $target_dir"
done
