#!/usr/bin/env python3
"""Patch karpathy-guidelines SKILL.md description after upstream sync."""

import sys
from pathlib import Path

import yaml

PATCHED_DESCRIPTION = """\
  Behavioral guidelines to reduce common LLM coding mistakes, from Karpathy's
  observations on coding pitfalls. Must be consulted whenever writing, reviewing,
  refactoring, or editing code — even a single-line fix benefits from these
  principles. Trigger on: any code change request ("add X", "fix Y", "implement Z",
  "refactor", "写代码", "修改", "实现"), code review, or when the user asks to
  edit/create files. If you're about to write or edit code, read this first."""


def patch_description(skill_path: Path) -> bool:
    content = skill_path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    if len(parts) < 3:
        print("  [patch] No YAML frontmatter found", file=sys.stderr)
        return False

    fm = yaml.safe_load(parts[1])
    if fm.get("description") == PATCHED_DESCRIPTION.strip():
        print("  [patch] Description already patched", file=sys.stderr)
        return False

    fm["description"] = PATCHED_DESCRIPTION.strip()
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=120).strip()
    new_content = f"---\n{new_fm}\n---{parts[2]}"
    skill_path.write_text(new_content, encoding="utf-8")
    return True


def main():
    candidate_paths = [
        Path("/media/yhr/2T/files/cc_projects/test/upstream/karpathy-skills/karpathy-guidelines/SKILL.md"),
        Path.home() / ".claude" / "skills" / "karpathy-guidelines" / "SKILL.md",
        Path.home() / ".agents" / "skills" / "karpathy-guidelines" / "SKILL.md",
    ]

    for p in candidate_paths:
        if p.exists():
            changed = patch_description(p)
            if changed:
                print(f"[patch] Patched: {p}")
            return 0

    print("[patch] karpathy-guidelines SKILL.md not found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
