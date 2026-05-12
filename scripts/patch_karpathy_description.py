#!/usr/bin/env python3
"""Patch karpathy-guidelines SKILL.md description after upstream sync.

Replaces the upstream description with a pushier version that triggers
on any code change request. Only the description field is changed;
the skill body updates from upstream are preserved.
"""

import sys
from pathlib import Path

PATCHED_DESCRIPTION = """\
  Behavioral guidelines to reduce common LLM coding mistakes, from Karpathy's
  observations on coding pitfalls. Must be consulted whenever writing, reviewing,
  refactoring, or editing code — even a single-line fix benefits from these
  principles. Trigger on: any code change request ("add X", "fix Y", "implement Z",
  "refactor", "写代码", "修改", "实现"), code review, or when the user asks to
  edit/create files. If you're about to write or edit code, read this first."""


def patch_description(skill_path: Path) -> bool:
    """Replace only the description field in YAML frontmatter. Returns True if changed."""
    content = skill_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    in_frontmatter = False
    in_description = False
    description_start = None
    description_end = None

    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            elif in_frontmatter and not in_description:
                # End of frontmatter — description wasn't found as a block,
                # check if it's a single-line field
                break
            elif in_description:
                description_end = i
                break
        elif in_frontmatter and line.startswith("description:"):
            rest = line[len("description:"):].strip()
            if rest and rest != "|":
                # Single-line description
                description_start = i
                description_end = i + 1
                break
            elif rest == "|":
                # Multi-line block scalar
                description_start = i
                description_end = None  # find end marker
                in_description = True

    if description_start is None:
        print("  [patch] Could not find description field", file=sys.stderr)
        return False

    # Find end of description block if multi-line
    if description_end is None and in_description:
        for j in range(description_start + 1, len(lines)):
            if lines[j].startswith("  ") or lines[j].strip() == "":
                # Check if this might be a de-dented next field
                stripped = lines[j].strip()
                if stripped and not stripped.startswith("-") and not lines[j].startswith("  "):
                    description_end = j
                    break
            else:
                description_end = j
                break
        if description_end is None:
            description_end = len(lines) - 1

    # Replace
    new_description_lines = ["description: |"]
    new_description_lines.extend(PATCHED_DESCRIPTION.split("\n"))
    new_lines = lines[:description_start] + new_description_lines + lines[description_end:]
    new_content = "\n".join(new_lines)

    if new_content == content:
        print("  [patch] Description already patched", file=sys.stderr)
        return False

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
