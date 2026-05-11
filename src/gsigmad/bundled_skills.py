"""Helpers for installing bundled SKILL.md assets into project-local directories."""
from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path


def _iter_skill_dirs(skills_root: Path):
    for child in sorted(skills_root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            yield child


def install_bundled_skills(project_root: Path, overwrite: bool = False) -> dict[str, list[str]]:
    """Copy packaged skill directories into local Claude/Codex skill paths."""
    installed: list[str] = []
    skipped: list[str] = []

    targets = [
        project_root / ".claude" / "skills",
        project_root / ".agents" / "skills",
    ]

    resources_root = files("gsigmad.skill_bundle").joinpath("skills")
    with as_file(resources_root) as resolved_root:
        skills_root = Path(resolved_root)
        for target_base in targets:
            target_base.mkdir(parents=True, exist_ok=True)
            for skill_dir in _iter_skill_dirs(skills_root):
                destination = target_base / skill_dir.name
                if destination.exists() and not overwrite:
                    skipped.append(str(destination))
                    continue
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(skill_dir, destination)
                installed.append(str(destination))

    return {"installed": installed, "skipped": skipped}
