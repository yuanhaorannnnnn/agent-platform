#!/usr/bin/env python3
"""Generate a local changelog for managed upstream skill repositories.

This cron job is intentionally local-only. `agent-upstream-sync.timer` owns
fetch/sync; this script records what changed in the already-managed caches.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "migration" / "upstream-manifest.yaml"
DISABLED_UPSTREAMS = ROOT / "state" / "disabled-upstreams.yaml"
CACHE_ROOT = Path.home() / ".agents" / "repos"
STATE_DIR = Path.home() / ".agents" / "upstream-changelog"
STATE_FILE = STATE_DIR / "state.json"
REPORT_DIR = STATE_DIR / "reports"


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def load_manifest() -> list[dict]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    return data.get("upstreams", [])


def load_disabled_upstreams() -> set[str]:
    if not DISABLED_UPSTREAMS.exists():
        return set()
    data = yaml.safe_load(DISABLED_UPSTREAMS.read_text(encoding="utf-8")) or {}
    return set((data.get("disabled") or {}).get("upstreams") or [])


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def repo_path(upstream: dict) -> Path:
    return CACHE_ROOT / upstream.get("cache_name", upstream["id"])


def changelog_for(repo: Path, old_head: str | None, new_head: str) -> list[str]:
    if not old_head or old_head == new_head:
        return []
    try:
        return run_git(repo, "log", "--oneline", "--decorate", f"{old_head}..{new_head}").splitlines()
    except subprocess.CalledProcessError:
        return [f"{old_head[:12]}..{new_head[:12]} (history unavailable)"]


def main() -> int:
    now = datetime.now()
    upstreams = load_manifest()
    disabled = load_disabled_upstreams()
    state = load_state()
    next_state = dict(state)
    report_lines = [
        f"# Upstream Changelog · {now:%Y-%m-%d %H:%M}",
        "",
    ]
    failures: list[str] = []
    changed = 0

    for upstream in upstreams:
        uid = upstream["id"]
        if uid in disabled:
            continue
        repo = repo_path(upstream)
        if not (repo / ".git").exists():
            failures.append(f"{uid}: missing cache {repo}")
            continue

        try:
            head = run_git(repo, "rev-parse", "HEAD")
            old = state.get(uid, {}).get("head")
            entries = changelog_for(repo, old, head)
            next_state[uid] = {
                "repo": upstream.get("repo", ""),
                "cache": str(repo),
                "head": head,
                "updated_at": now.isoformat(timespec="seconds"),
            }
            if entries:
                changed += 1
                report_lines.extend([f"## {uid}", ""])
                report_lines.extend(f"- `{line}`" for line in entries)
                report_lines.append("")
        except Exception as exc:
            failures.append(f"{uid}: {exc}")

    if changed == 0:
        report_lines.append("No upstream HEAD changes since last recorded run.")
        report_lines.append("")

    if failures:
        report_lines.extend(["## Failures", ""])
        report_lines.extend(f"- {item}" for item in failures)
        report_lines.append("")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"upstream-changelog-{now:%Y-%m-%d}.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    save_state(next_state)
    print(f"wrote {report_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
