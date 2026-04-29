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
    def test_load_manifest_returns_tracked_skills(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.yaml"
            manifest_path.write_text(
                yaml.safe_dump(
                    {
                        "upstreams": [
                            {
                                "id": "anthropics-skills",
                                "repo": "https://example.com/repo.git",
                                "branch": "main",
                                "tracked_skills": [
                                    {
                                        "name": "pdf",
                                        "source_path": "skills/pdf",
                                        "local_path": "agent-platform/skills/pdf",
                                        "sync_policy": "track_upstream",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            upstream = module.load_upstream_manifest(manifest_path, "anthropics-skills")

        self.assertEqual(upstream["repo"], "https://example.com/repo.git")
        self.assertEqual(upstream["branch"], "main")
        self.assertEqual(upstream["tracked_skills"][0]["name"], "pdf")

    def test_manifest_keeps_noisy_upstreams_curated(self) -> None:
        module = load_module()

        manifest_path = REPO_ROOT / "migration" / "upstream-manifest.yaml"
        superpowers = module.load_upstream_manifest(manifest_path, "superpowers-lite")
        karpathy = module.load_upstream_manifest(manifest_path, "karpathy-skills")

        self.assertEqual(
            [skill["name"] for skill in superpowers["tracked_skills"]],
            ["test-driven-development"],
        )
        self.assertEqual(
            [skill["name"] for skill in karpathy["tracked_skills"]],
            ["karpathy-guidelines"],
        )

    def test_sync_skill_copies_selected_directory(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_repo = tmp_path / "source-repo"
            source_skill = source_repo / "skills" / "pdf"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text("name: pdf\n", encoding="utf-8")
            (source_skill / "reference.md").write_text("reference", encoding="utf-8")

            destination_root = tmp_path / "destination"
            skill = {
                "name": "pdf",
                "source_path": "skills/pdf",
            }

            result = module.sync_skill(source_repo, destination_root, skill)

            self.assertEqual(result["status"], "updated")
            self.assertTrue((destination_root / "pdf" / "SKILL.md").exists())
            self.assertEqual(
                (destination_root / "pdf" / "reference.md").read_text(encoding="utf-8"),
                "reference",
            )

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
            snapshot_skill = snapshot_root / "skill-creator"
            snapshot_skill.mkdir(parents=True)
            (snapshot_skill / "SKILL.md").write_text("name: skill-creator\n", encoding="utf-8")

            local_root = tmp_path / "agent-platform" / "skills"
            skill = {
                "name": "skill-creator",
                "local_path": "agent-platform/skills/skill-creator",
            }

            result = module.promote_skill(snapshot_root, local_root, skill)

            self.assertEqual(result["status"], "updated")
            self.assertTrue((local_root / "skill-creator" / "SKILL.md").exists())

    def test_promote_all_skills_returns_per_skill_results(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_root = tmp_path / "upstream"
            for skill_name in ("pdf", "pptx"):
                skill_dir = snapshot_root / skill_name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text(f"name: {skill_name}\n", encoding="utf-8")

            local_root = tmp_path / "agent-platform" / "skills"
            tracked_skills = [
                {"name": "pdf", "local_path": "agent-platform/skills/pdf"},
                {"name": "pptx", "local_path": "agent-platform/skills/pptx"},
            ]

            results = module.promote_skills(snapshot_root, local_root, tracked_skills)

            self.assertEqual([item["name"] for item in results], ["pdf", "pptx"])
            self.assertEqual([item["status"] for item in results], ["updated", "updated"])

    def test_sync_enabled_skills_includes_snapshot_only_entries(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "pdf", "sync_policy": "track_upstream"},
            {"name": "planning-with-files", "sync_policy": "track_snapshot"},
        ]

        enabled = module.sync_enabled_skills(tracked_skills)

        self.assertEqual([item["name"] for item in enabled], ["pdf", "planning-with-files"])

    def test_sync_enabled_skills_skips_disabled_skill(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "pdf", "sync_policy": "track_upstream"},
            {"name": "docx", "sync_policy": "track_upstream"},
        ]
        disabled = {"skills": {"anthropics-skills": ["docx"]}}

        enabled = module.sync_enabled_skills(tracked_skills, "anthropics-skills", disabled)

        self.assertEqual([item["name"] for item in enabled], ["pdf"])

    def test_is_upstream_disabled_reads_disabled_upstreams(self) -> None:
        module = load_module()

        disabled = {"upstreams": ["anthropics-skills"]}

        self.assertTrue(module.is_upstream_disabled("anthropics-skills", disabled))
        self.assertFalse(module.is_upstream_disabled("gstack-repo", disabled))

    def test_promotable_skills_skip_snapshot_only_entries(self) -> None:
        module = load_module()

        tracked_skills = [
            {"name": "pdf", "sync_policy": "track_upstream"},
            {"name": "planning-with-files", "sync_policy": "track_snapshot"},
        ]

        promotable = module.promotable_skills(tracked_skills)

        self.assertEqual([item["name"] for item in promotable], ["pdf"])

    def test_install_links_only_manages_agents_skills_and_cleans_codex_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_skills = home / ".codex" / "skills"
            codex_skills.mkdir(parents=True)
            upstream_root = REPO_ROOT / "upstream"
            anthropic_docx = upstream_root / "anthropics-skills" / "docx"
            # docx must exist in the real upstream snapshot
            self.assertTrue(anthropic_docx.is_dir(), "anthropics-skills/docx must exist for this test")
            stale_target = REPO_ROOT / "upstream" / "anthropics-skills" / "docx"
            (codex_skills / "docx").symlink_to(stale_target)

            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }
            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((codex_skills / "docx").exists())
            self.assertTrue((home / ".agents" / "skills" / "docx").is_symlink())
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
            (claude_skills / "save-conversation").symlink_to(REPO_ROOT / "upstream" / "anthropics-skills" / "pdf")
            nested_docx_dir = claude_skills / "docx"
            nested_docx_dir.mkdir()
            (nested_docx_dir / "docx").symlink_to(REPO_ROOT / "upstream" / "anthropics-skills" / "docx")

            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }
            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((claude_agents / "repo-agents").exists())
            self.assertFalse((claude_commands / "repo-commands").exists())
            self.assertFalse((claude_skills / "save-conversation").exists())
            self.assertFalse((nested_docx_dir / "docx").exists())

    def test_install_links_does_not_expose_untracked_gstack_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {
                **subprocess.os.environ,
                "HOME": str(home),
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".agents" / "skills" / "gstack").exists())

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
            (existing_skills / "docx").symlink_to(REPO_ROOT / "upstream" / "anthropics-skills" / "docx")
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "skills": {
                                "anthropics-skills": ["docx"],
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

            self.assertFalse((home / ".agents" / "skills" / "docx").exists())
            self.assertTrue((home / ".agents" / "skills" / "pdf").is_symlink())

    def test_install_links_skips_disabled_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "upstreams": ["anthropics-skills"],
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

            self.assertFalse((home / ".agents" / "skills" / "docx").exists())
            self.assertFalse((home / ".agents" / "skills" / "pdf").exists())

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
                                "codex": {
                                    "skills": {
                                        "anthropics-skills": ["docx"],
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
                "SKILL_AGENT_TARGETS": "codex",
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".codex" / "skills" / "docx").exists())
            self.assertTrue((home / ".codex" / "skills" / "pdf").is_symlink())
            self.assertFalse((home / ".agents" / "skills" / "pdf").exists())

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
                                "codex": {
                                    "skills": {
                                        "anthropics-skills": ["docx"],
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

            self.assertTrue((home / ".agents" / "skills" / "docx").is_symlink())
            self.assertTrue((home / ".agents" / "skills" / "pdf").is_symlink())

    def test_install_links_supports_pi_agent_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            disabled_file = tmp_path / "disabled-upstreams.yaml"
            disabled_file.write_text(
                yaml.safe_dump(
                    {
                        "disabled": {
                            "agents": {
                                "pi": {
                                    "skills": {
                                        "anthropics-skills": ["docx"],
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
                "SKILL_AGENT_TARGETS": "pi",
            }

            subprocess.run(["bash", str(INSTALL_LINKS_PATH)], check=True, env=env)

            self.assertFalse((home / ".pi" / "agent" / "skills" / "docx").exists())
            self.assertTrue((home / ".pi" / "agent" / "skills" / "pdf").is_symlink())

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
