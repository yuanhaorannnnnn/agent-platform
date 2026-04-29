#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
from pathlib import Path

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
AGENT_PLATFORM_DIR = SCRIPT_DIR.parent
DEFAULT_MANIFEST = AGENT_PLATFORM_DIR / "migration" / "upstream-manifest.yaml"
DEFAULT_CACHE_ROOT = Path.home() / ".agents" / "repos"
DEFAULT_SYNC_ROOT = AGENT_PLATFORM_DIR / "upstream"
DEFAULT_LOCAL_SKILLS_ROOT = AGENT_PLATFORM_DIR / "skills"
DEFAULT_DISABLED_UPSTREAMS = AGENT_PLATFORM_DIR / "state" / "disabled-upstreams.yaml"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def load_upstream_manifest(manifest_path: Path, upstream_id: str) -> dict:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    for upstream in data.get("upstreams", []):
        if upstream.get("id") == upstream_id:
            return upstream
    raise ValueError(f"upstream '{upstream_id}' not found in {manifest_path}")


def load_disabled_upstreams(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    disabled = data.get("disabled", {}) if isinstance(data, dict) else {}
    return disabled if isinstance(disabled, dict) else {}


def is_upstream_disabled(upstream_id: str, disabled: dict) -> bool:
    return upstream_id in set(disabled.get("upstreams") or [])


def is_skill_disabled(upstream_id: str, skill_name: str, disabled: dict) -> bool:
    disabled_skills = disabled.get("skills") or {}
    return skill_name in set(disabled_skills.get(upstream_id) or [])


def clone_or_update_repo(repo_url: str, branch: str, cache_dir: Path) -> str:
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    if not cache_dir.exists():
        run(["git", "clone", "--branch", branch, "--single-branch", repo_url, str(cache_dir)])
    else:
        run(["git", "fetch", "origin", branch], cwd=cache_dir)
        run(["git", "checkout", branch], cwd=cache_dir)
        run(["git", "pull", "--ff-only", "origin", branch], cwd=cache_dir)
    return run(["git", "rev-parse", "HEAD"], cwd=cache_dir)


def directories_equal(left: Path, right: Path) -> bool:
    comparison = filecmp.dircmp(left, right)
    if comparison.left_only or comparison.right_only or comparison.diff_files or comparison.funny_files:
        return False
    return all(
        directories_equal(left / subdir, right / subdir)
        for subdir in comparison.common_dirs
    )


def sync_skill(source_repo: Path, destination_root: Path, skill: dict) -> dict:
    source_dir = source_repo / skill["source_path"]
    destination_dir = destination_root / skill["name"]

    if not source_dir.exists():
        return {
            "name": skill["name"],
            "status": "missing",
            "source": str(source_dir),
            "destination": str(destination_dir),
        }

    destination_root.mkdir(parents=True, exist_ok=True)
    if destination_dir.exists() and directories_equal(source_dir, destination_dir):
        return {
            "name": skill["name"],
            "status": "unchanged",
            "source": str(source_dir),
            "destination": str(destination_dir),
        }

    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    return {
        "name": skill["name"],
        "status": "updated",
        "source": str(source_dir),
        "destination": str(destination_dir),
    }


def ignore_repo_metadata(_: str, names: list[str]) -> set[str]:
    ignored = {".git", ".gitignore"}
    return {name for name in names if name in ignored}


def sync_repo_snapshot(source_repo: Path, destination_root: Path) -> dict:
    destination_root.parent.mkdir(parents=True, exist_ok=True)

    if destination_root.exists() and directories_equal(
        source_repo,
        destination_root,
    ):
        return {
            "status": "unchanged",
            "source": str(source_repo),
            "destination": str(destination_root),
        }

    if destination_root.exists():
        shutil.rmtree(destination_root)

    shutil.copytree(
        source_repo,
        destination_root,
        ignore=ignore_repo_metadata,
    )
    return {
        "status": "updated",
        "source": str(source_repo),
        "destination": str(destination_root),
    }


def promote_skill(snapshot_root: Path, local_skills_root: Path, skill: dict) -> dict:
    source_dir = snapshot_root / skill["name"]
    local_path = Path(skill.get("local_path", ""))
    destination_name = local_path.name if local_path.name else skill["name"]
    destination_dir = local_skills_root / destination_name

    if not source_dir.exists():
        return {
            "name": skill["name"],
            "status": "missing",
            "source": str(source_dir),
            "destination": str(destination_dir),
        }

    local_skills_root.mkdir(parents=True, exist_ok=True)
    if destination_dir.exists() and directories_equal(source_dir, destination_dir):
        return {
            "name": skill["name"],
            "status": "unchanged",
            "source": str(source_dir),
            "destination": str(destination_dir),
        }

    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(source_dir, destination_dir)
    return {
        "name": skill["name"],
        "status": "updated",
        "source": str(source_dir),
        "destination": str(destination_dir),
    }


def promote_skills(snapshot_root: Path, local_skills_root: Path, tracked_skills: list[dict]) -> list[dict]:
    return [promote_skill(snapshot_root, local_skills_root, skill) for skill in tracked_skills]


def sync_enabled_skills(tracked_skills: list[dict], upstream_id: str = "", disabled: dict | None = None) -> list[dict]:
    disabled = disabled or {}
    return [
        skill
        for skill in tracked_skills
        if skill.get("sync_policy", "track_upstream") in {"track_upstream", "track_snapshot"}
        and not is_skill_disabled(upstream_id, skill.get("name", ""), disabled)
    ]


def promotable_skills(tracked_skills: list[dict]) -> list[dict]:
    return [skill for skill in tracked_skills if skill.get("sync_policy", "track_upstream") == "track_upstream"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync tracked upstream skills into a local cache.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to upstream manifest YAML")
    parser.add_argument("--upstream-id", default="anthropics-skills", help="Manifest upstream id to sync")
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT, help="Directory holding cached upstream git repos")
    parser.add_argument("--sync-root", type=Path, default=DEFAULT_SYNC_ROOT, help="Directory to store synced upstream skill snapshots")
    parser.add_argument("--local-skills-root", type=Path, default=DEFAULT_LOCAL_SKILLS_ROOT, help="Directory holding repo-managed local skills")
    parser.add_argument("--disabled-upstreams", type=Path, default=DEFAULT_DISABLED_UPSTREAMS, help="Path to disabled upstreams YAML")
    parser.add_argument("--promote-to-local", action="store_true", help="Copy synced upstream snapshots into the repo-managed local skills directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    upstream = load_upstream_manifest(args.manifest, args.upstream_id)
    disabled = load_disabled_upstreams(args.disabled_upstreams)
    if is_upstream_disabled(args.upstream_id, disabled):
        print(f"Upstream disabled: {args.upstream_id}")
        return 0
    tracked_skills = sync_enabled_skills(upstream.get("tracked_skills", []), args.upstream_id, disabled)
    local_promotable = promotable_skills(tracked_skills)

    cache_name = upstream.get("cache_name", args.upstream_id)
    cache_dir = args.cache_root / cache_name
    sync_root = args.sync_root / args.upstream_id
    head = clone_or_update_repo(upstream["repo"], upstream.get("branch", "main"), cache_dir)

    print(f"Synced upstream repo: {upstream['repo']}")
    print(f"Upstream head: {head}")
    print(f"Snapshot root: {sync_root}")

    for skill in tracked_skills:
        result = sync_skill(cache_dir, sync_root, skill)
        print(f"{result['name']}: {result['status']}")

    if args.promote_to_local:
        print(f"Promoting snapshots into: {args.local_skills_root}")
        for result in promote_skills(sync_root, args.local_skills_root, local_promotable):
            print(f"{result['name']} -> local: {result['status']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
