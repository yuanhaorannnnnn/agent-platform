from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync_upstream_skills.py"
INSTALL_LINKS_PATH = REPO_ROOT / "scripts" / "install_links.sh"
SYNC_ALL_PATH = REPO_ROOT / "scripts" / "sync_all_upstreams.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sync_upstream_skills", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_sync_all_module():
    scripts_dir = str(SYNC_ALL_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("sync_all_upstreams", SYNC_ALL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SyncUpstreamSkillsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_tmp = tempfile.TemporaryDirectory()
        fixture_root = Path(cls.fixture_tmp.name)
        cls.fixture_upstream_root = fixture_root / "upstream"
        fixture_skills = (
            ("alpha-upstream", "alpha-skill"),
            ("beta-upstream", "beta-skill"),
        )
        for upstream_id, skill_name in fixture_skills:
            skill_dir = cls.fixture_upstream_root / upstream_id / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"name: {skill_name}\n",
                encoding="utf-8",
            )

        cls.fixture_manifest = fixture_root / "manifest.yaml"
        cls.fixture_manifest.write_text(
            yaml.safe_dump(
                {
                    "upstreams": [
                        {
                            "id": upstream_id,
                            "tracked_skills": [{"name": skill_name}],
                        }
                        for upstream_id, skill_name in fixture_skills
                    ]
                }
            ),
            encoding="utf-8",
        )
        cls.old_upstream_root = os.environ.get("UPSTREAM_ROOT_PATH")
        cls.old_manifest = os.environ.get("UPSTREAM_MANIFEST_PATH")
        os.environ["UPSTREAM_ROOT_PATH"] = str(cls.fixture_upstream_root)
        os.environ["UPSTREAM_MANIFEST_PATH"] = str(cls.fixture_manifest)

    @classmethod
    def tearDownClass(cls) -> None:
        old_values = (
            ("UPSTREAM_ROOT_PATH", cls.old_upstream_root),
            ("UPSTREAM_MANIFEST_PATH", cls.old_manifest),
        )
        for key, old_value in old_values:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        cls.fixture_tmp.cleanup()
    def test_load_manifest_returns_tracked_skills(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.yaml"
            manifest_path.write_text(
                yaml.safe_dump(
                    {
                        "upstreams": [
                            {
                                "id": "sample-upstream",
                                "repo": "https://example.com/repo.git",
                                "branch": "main",
                                "tracked_skills": [
                                    {
                                        "name": "sample-skill",
                                        "source_path": "skills/sample-skill",
                                        "local_path": "agent-platform/skills/sample-skill",
                                        "sync_policy": "track_upstream",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            upstream = module.load_upstream_manifest(manifest_path, "sample-upstream")

        self.assertEqual(upstream["repo"], "https://example.com/repo.git")
        self.assertEqual(upstream["branch"], "main")
        self.assertEqual(upstream["tracked_skills"][0]["name"], "sample-skill")

    def test_manifest_contains_only_retained_upstreams(self) -> None:
        manifest_path = REPO_ROOT / "migration" / "upstream-manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            [upstream["id"] for upstream in manifest["upstreams"]],
            ["agent-skills", "ljg-skills", "impeccable", "ponytail", "hairline"],
        )

    def test_pinned_revision_survives_upstream_advance_and_preserves_dirty_cache(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            origin = Path(tmp) / "origin"
            cache = Path(tmp) / "cache"
            module.run(["git", "init", "-b", "main", str(origin)])
            module.run(["git", "config", "user.email", "test@example.invalid"], cwd=origin)
            module.run(["git", "config", "user.name", "test"], cwd=origin)
            (origin / "version").write_text("one")
            module.run(["git", "add", "version"], cwd=origin)
            module.run(["git", "commit", "-m", "one"], cwd=origin)
            pinned = module.run(["git", "rev-parse", "HEAD"], cwd=origin)
            self.assertEqual(module.clone_or_update_repo(str(origin), "main", cache, pinned), pinned)
            (origin / "version").write_text("two")
            module.run(["git", "commit", "-am", "two"], cwd=origin)
            latest = module.run(["git", "rev-parse", "HEAD"], cwd=origin)
            self.assertEqual(module.clone_or_update_repo(str(origin), "main", cache, pinned), pinned)
            self.assertEqual((cache / "version").read_text(), "one")
            self.assertEqual(module.clone_or_update_repo(str(origin), "main", cache), latest)
            (cache / "version").write_text("local work")
            with self.assertRaisesRegex(ValueError, "local changes"):
                module.clone_or_update_repo(str(origin), "main", cache, pinned)
            self.assertEqual((cache / "version").read_text(), "local work")
            with self.assertRaisesRegex(ValueError, "full lowercase"):
                module.clone_or_update_repo(str(origin), "main", cache, "main")

    def test_sync_skill_copies_selected_directory(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_repo = tmp_path / "source-repo"
            source_skill = source_repo / "skills" / "sample-skill"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text("name: sample-skill\n", encoding="utf-8")
            (source_skill / "reference.md").write_text("reference", encoding="utf-8")

            destination_root = tmp_path / "destination"
            skill = {
                "name": "sample-skill",
                "source_path": "skills/sample-skill",
            }

            result = module.sync_skill(source_repo, destination_root, skill)

            self.assertEqual(result["status"], "updated")
            self.assertTrue((destination_root / "sample-skill" / "SKILL.md").exists())
            self.assertEqual(
                (destination_root / "sample-skill" / "reference.md").read_text(encoding="utf-8"),
                "reference",
            )

    def test_sync_skill_removes_configured_frontmatter_keys(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_repo = tmp_path / "source-repo"
            source_skill = source_repo / "skills" / "ponytail"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text(
                "---\nname: ponytail\nargument-hint: '[lite|full]'\nlicense: MIT\n---\n# Ponytail\n",
                encoding="utf-8",
            )
            destination_root = tmp_path / "destination"
            skill = {
                "name": "ponytail",
                "source_path": "skills/ponytail",
                "frontmatter_remove_keys": ["argument-hint"],
            }

            first = module.sync_skill(source_repo, destination_root, skill)
            synced = (destination_root / "ponytail" / "SKILL.md").read_text(encoding="utf-8")
            second = module.sync_skill(source_repo, destination_root, skill)

            self.assertEqual(first["status"], "updated")
            self.assertNotIn("argument-hint", synced)
            self.assertIn("license: MIT", synced)
            self.assertEqual(second["status"], "unchanged")

    def test_sync_skill_appends_managed_markdown(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_repo = tmp_path / "source-repo"
            source_skill = source_repo / "skills" / "ponytail"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text(
                "---\nname: ponytail\n---\n\n# Ponytail\n",
                encoding="utf-8",
            )
            destination_root = tmp_path / "destination"
            skill = {
                "name": "ponytail",
                "source_path": "skills/ponytail",
                "skill_md_append": "## Post-build ablation\n\nMinimum sufficient.",
            }

            first = module.sync_skill(source_repo, destination_root, skill)
            synced = (destination_root / "ponytail" / "SKILL.md").read_text(encoding="utf-8")
            second = module.sync_skill(source_repo, destination_root, skill)

            self.assertEqual(first["status"], "updated")
            self.assertEqual(synced.count("## Post-build ablation"), 1)
            self.assertEqual(second["status"], "unchanged")

    def test_manifest_upstreams_declare_ownership_policy(self) -> None:
        manifest = yaml.safe_load(
            (REPO_ROOT / "migration" / "upstream-manifest.yaml").read_text(encoding="utf-8")
        )
        for upstream in manifest["upstreams"]:
            with self.subTest(upstream=upstream["id"]):
                self.assertIn(upstream.get("ownership"), {"owned", "forked", "subscribed"})
                self.assertIn(upstream.get("update_policy"), {"pinned", "tracking"})
                self.assertIsInstance(upstream.get("local_patch"), bool)

    def test_sync_repo_snapshot_copies_repo_contents_except_git_metadata(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_repo = tmp_path / "source-repo"
            (source_repo / "skills" / "sample-skill").mkdir(parents=True)
            (source_repo / "scripts").mkdir(parents=True)
            (source_repo / ".git").mkdir()
            (source_repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            (source_repo / "skills" / "sample-skill" / "SKILL.md").write_text("name: sample-skill\n", encoding="utf-8")
            (source_repo / "scripts" / "sample_tool.py").write_text("print('ok')\n", encoding="utf-8")

            destination_root = tmp_path / "snapshot"

            result = module.sync_repo_snapshot(source_repo, destination_root)

            self.assertEqual(result["status"], "updated")
            self.assertTrue((destination_root / "skills" / "sample-skill" / "SKILL.md").exists())
            self.assertTrue((destination_root / "scripts" / "sample_tool.py").exists())
            self.assertFalse((destination_root / ".git").exists())
            self.assertFalse((destination_root / ".gitignore").exists())

    def test_promote_skill_uses_local_path_basename(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_root = tmp_path / "upstream"
            snapshot_skill = snapshot_root / "sample-promoted-skill"
            snapshot_skill.mkdir(parents=True)
            (snapshot_skill / "SKILL.md").write_text("name: sample-promoted-skill\n", encoding="utf-8")

            local_root = tmp_path / "agent-platform" / "skills"
            skill = {
                "name": "sample-promoted-skill",
                "local_path": "agent-platform/skills/sample-promoted-skill",
            }

            result = module.promote_skill(snapshot_root, local_root, skill)

            self.assertEqual(result["status"], "updated")
            self.assertTrue((local_root / "sample-promoted-skill" / "SKILL.md").exists())

    def test_promote_all_skills_returns_per_skill_results(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_root = tmp_path / "upstream"
            for skill_name in ("alpha-skill", "beta-skill"):
                skill_dir = snapshot_root / skill_name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"name: {skill_name}\n", encoding="utf-8")

            local_root = tmp_path / "agent-platform" / "skills"
            tracked_skills = [
                {"name": "alpha-skill", "local_path": "agent-platform/skills/alpha-skill"},
                {"name": "beta-skill", "local_path": "agent-platform/skills/beta-skill"},
            ]

            results = module.promote_skills(snapshot_root, local_root, tracked_skills)

            self.assertEqual([item["name"] for item in results], ["alpha-skill", "beta-skill"])
            self.assertEqual([item["status"] for item in results], ["updated", "updated"])

    def test_sync_enabled_skills_includes_snapshot_only_entries(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "alpha-skill", "sync_policy": "track_upstream"},
            {"name": "planning-with-files", "sync_policy": "track_snapshot"},
        ]

        enabled = module.sync_enabled_skills(tracked_skills)

        self.assertEqual([item["name"] for item in enabled], ["alpha-skill", "planning-with-files"])

    def test_sync_enabled_skills_skips_disabled_skill(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "alpha-skill", "sync_policy": "track_upstream"},
            {"name": "beta-skill", "sync_policy": "track_upstream"},
        ]
        disabled = {"skills": {"sample-upstream": ["beta-skill"]}}

        enabled = module.sync_enabled_skills(tracked_skills, "sample-upstream", disabled)

        self.assertEqual([item["name"] for item in enabled], ["alpha-skill"])

    def test_is_upstream_disabled_reads_disabled_upstreams(self) -> None:
        module = load_module()

        disabled = {"upstreams": ["sample-upstream"]}

        self.assertTrue(module.is_upstream_disabled("sample-upstream", disabled))
        self.assertFalse(module.is_upstream_disabled("untracked-upstream", disabled))

    def test_promotable_skills_skip_snapshot_only_entries(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "alpha-skill", "sync_policy": "track_upstream"},
            {"name": "planning-with-files", "sync_policy": "track_snapshot"},
        ]

        promotable = module.promotable_skills(tracked_skills)

        self.assertEqual([item["name"] for item in promotable], ["alpha-skill"])

    def test_install_links_only_manages_agents_skills_and_cleans_codex_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_skills = home / ".codex" / "skills"
            codex_skills.mkdir(parents=True)
            upstream_root = self.fixture_upstream_root
            tdd_skill = upstream_root / "alpha-upstream" / "alpha-skill"
            self.assertTrue(tdd_skill.is_dir(), "alpha-upstream/alpha-skill must exist for this test")
            (codex_skills / "alpha-skill").symlink_to(tdd_skill)

            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }
            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((codex_skills / "alpha-skill").exists())
            self.assertTrue((home / ".agents" / "skills" / "alpha-skill").is_symlink())
            self.assertFalse((home / ".claude" / "agents" / "repo-agents").exists())
            self.assertFalse((home / ".claude" / "commands" / "repo-commands").exists())

    def test_install_links_cleans_repo_managed_claude_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            claude_agents = home / ".claude" / "agents"
            claude_commands = home / ".claude" / "commands"
            claude_skills = home / ".claude" / "skills"
            claude_agents.mkdir(parents=True)
            claude_commands.mkdir(parents=True)
            claude_skills.mkdir(parents=True)
            (claude_agents / "repo-agents").symlink_to(REPO_ROOT / "scripts")
            (claude_commands / "repo-commands").symlink_to(REPO_ROOT / "scripts")
            (claude_skills / "save-conversation").symlink_to(REPO_ROOT / "upstream" / "alpha-upstream" / "alpha-skill")
            (claude_skills / "beta-skill").symlink_to(REPO_ROOT / "upstream" / "beta-upstream" / "beta-skill")

            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }
            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((claude_agents / "repo-agents").exists())
            self.assertFalse((claude_commands / "repo-commands").exists())
            self.assertFalse((claude_skills / "save-conversation").exists())
            # Cleaned symlinks are re-created from upstream
            self.assertTrue((claude_skills / "alpha-skill").is_symlink())
            self.assertTrue((claude_skills / "beta-skill").is_symlink())

    def test_install_links_does_not_expose_upstream_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".agents" / "skills" / "alpha-upstream").exists())

    def test_install_links_preserves_non_symlink_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            existing = home / ".agents" / "skills" / "alpha-skill"
            existing.mkdir(parents=True)
            marker = existing / "local-marker"
            marker.write_text("keep", encoding="utf-8")
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
                "SKILL_AGENT_TARGETS": "agents",
            }

            result = subprocess.run(
                ["bash", str(INSTALL_LINKS_PATH)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(existing.is_dir())
            self.assertFalse(existing.is_symlink())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertIn("Refusing to replace non-symlink", result.stderr)

    def test_install_links_skips_managed_install_upstreams(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".agents" / "skills" / "save-conversation").exists())

    def test_install_links_skips_disabled_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            existing_skills = home / ".agents" / "skills"
            existing_skills.mkdir(parents=True)
            (existing_skills / "alpha-skill").symlink_to(REPO_ROOT / "upstream" / "alpha-upstream" / "alpha-skill")
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "skills": {
                                "alpha-upstream": ["alpha-skill"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
                "DISABLED_UPSTREAMS_PATH": str(disabled_file),
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".agents" / "skills" / "alpha-skill").exists())
            self.assertTrue((home / ".agents" / "skills" / "beta-skill").is_symlink())

    def test_install_links_skips_disabled_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "upstreams": ["alpha-upstream"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
                "DISABLED_UPSTREAMS_PATH": str(disabled_file),
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".agents" / "skills" / "alpha-skill").exists())
            self.assertTrue((home / ".agents" / "skills" / "beta-skill").is_symlink())

    def test_install_links_skips_agent_scoped_disabled_skill_only_for_target_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "agents": {
                                "claude": {
                                    "skills": {
                                        "beta-upstream": ["beta-skill"],
                                    },
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
                "DISABLED_UPSTREAMS_PATH": str(disabled_file),
                "SKILL_AGENT_TARGETS": "claude",
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".claude" / "skills" / "beta-skill").exists())
            self.assertTrue((home / ".claude" / "skills" / "alpha-skill").is_symlink())
            self.assertFalse((home / ".agents" / "skills" / "alpha-skill").exists())

    def test_install_links_agent_scoped_disabled_skill_does_not_affect_shared_agents_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "agents": {
                                "claude": {
                                    "skills": {
                                        "beta-upstream": ["beta-skill"],
                                    },
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
                "DISABLED_UPSTREAMS_PATH": str(disabled_file),
                "SKILL_AGENT_TARGETS": "agents",
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertTrue((home / ".agents" / "skills" / "beta-skill").is_symlink())
            self.assertTrue((home / ".agents" / "skills" / "alpha-skill").is_symlink())

    def test_run_managed_install_executes_upstream_installer(self) -> None:
        module = load_sync_all_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_dir = tmp_path / "agent-skills"
            scripts_dir = cache_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            install_script = scripts_dir / "install.sh"
            install_script.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\nmkdir -p \"$HOME/.agents/skills\"\nprintf 'ok' > \"$HOME/.agents/skills/installed-marker\"\n",
                encoding="utf-8",
            )
            install_script.chmod(0o755)

            old_home = os.environ.get("HOME")
            os.environ["HOME"] = str(tmp_path)
            try:
                result = module.run_managed_install(
                    cache_dir,
                    {
                        "id": "agent-skills",
                        "install": {
                            "cwd": ".",
                            "command": ["bash", "scripts/install.sh"],
                            "runtime_dir": "~/.agents/skills",
                        },
                    },
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(result["runtime_dir"], str(tmp_path / ".agents" / "skills"))
            self.assertTrue((tmp_path / ".agents" / "skills" / "installed-marker").exists())


if __name__ == "__main__":
    unittest.main()
