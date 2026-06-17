#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

from sync_upstream_skills import (
    clone_or_update_repo,
    is_upstream_disabled,
    load_disabled_upstreams,
    promote_skills,
    promotable_skills,
    sync_enabled_skills,
    sync_skill,
)


SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_PLATFORM_DIR = SCRIPT_DIR.parent
DEFAULT_MANIFEST = AGENT_PLATFORM_DIR / "migration" / "upstream-manifest.yaml"
DEFAULT_CACHE_ROOT = Path.home() / ".agents" / "repos"
DEFAULT_SYNC_ROOT = AGENT_PLATFORM_DIR / "upstream"
DEFAULT_LOCAL_SKILLS_ROOT = AGENT_PLATFORM_DIR / "skills"
DEFAULT_DISABLED_UPSTREAMS = AGENT_PLATFORM_DIR / "state" / "disabled-upstreams.yaml"
INSTALL_LINKS = SCRIPT_DIR / "install_links.sh"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync every upstream defined in the manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to upstream manifest YAML")
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT, help="Directory holding cached upstream git repos")
    parser.add_argument("--sync-root", type=Path, default=DEFAULT_SYNC_ROOT, help="Directory to store synced upstream skill snapshots")
    parser.add_argument("--local-skills-root", type=Path, default=DEFAULT_LOCAL_SKILLS_ROOT, help="Directory holding repo-managed local skills")
    parser.add_argument("--disabled-upstreams", type=Path, default=DEFAULT_DISABLED_UPSTREAMS, help="Path to disabled upstreams YAML")
    parser.add_argument("--promote-to-local", action="store_true", help="Copy sync_policy=track_upstream skills into the repo-managed local skills directory")
    parser.add_argument("--relink", action="store_true", help="Run install_links.sh after syncing")
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("upstreams", [])


def run_links() -> None:
    subprocess.run([str(INSTALL_LINKS)], check=True)


def main() -> int:
    import sys

    args = parse_args()
    upstreams = load_manifest(args.manifest)
    disabled = load_disabled_upstreams(args.disabled_upstreams)
    failed: list[str] = []

    for upstream in upstreams:
        upstream_id = upstream["id"]
        try:
            if is_upstream_disabled(upstream_id, disabled):
                print(f"[{upstream_id}] disabled")
                print("")
                continue
            tracked_skills = sync_enabled_skills(upstream.get("tracked_skills", []), upstream_id, disabled)
            local_promotable = promotable_skills(tracked_skills)

            cache_name = upstream.get("cache_name", upstream_id)
            cache_dir = args.cache_root / cache_name
            sync_root = args.sync_root / upstream_id
            head = clone_or_update_repo(upstream["repo"], upstream.get("branch", "main"), cache_dir)

            print(f"[{upstream_id}] Synced upstream repo: {upstream['repo']}")
            print(f"[{upstream_id}] Upstream head: {head}")
            print(f"[{upstream_id}] Snapshot root: {sync_root}")

            # ponytail: run install command if present, then sync tracked_skills as snapshot
            install = upstream.get("install") or {}
            cmd = install.get("command")
            if cmd:
                cwd = cache_dir / install.get("cwd", ".")
                subprocess.run(cmd, cwd=cwd, text=True, check=True)
                print(f"[{upstream_id}] ran install: {cmd}")

            for skill in tracked_skills:
                result = sync_skill(cache_dir, sync_root, skill)
                print(f"[{upstream_id}] {result['name']}: {result['status']}")

            if args.promote_to_local:
                print(f"[{upstream_id}] Promoting snapshots into: {args.local_skills_root}")
                for result in promote_skills(sync_root, args.local_skills_root, local_promotable):
                    print(f"[{upstream_id}] {result['name']} -> local: {result['status']}")

            print("")
        except Exception as exc:
            print(f"[{upstream_id}] ERROR: {exc}", file=sys.stderr)
            failed.append(upstream_id)
            print("")

    if args.relink:
        try:
            run_links()
            print("Relinked ~/.agents/skills from managed snapshots.")
        except Exception as exc:
            print(f"[relink] ERROR: {exc}", file=sys.stderr)
            failed.append("relink")

    if failed:
        print(f"\nSync completed with failures: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
