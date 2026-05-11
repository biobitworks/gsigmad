"""Tests for the npm thin shim."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def test_npm_shim_delegates_to_python(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "args.txt"
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > \"{marker}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    subprocess.run(
        ["node", "npm/bin/gsigmad.js", "--version"],
        cwd=repo_root,
        env=env,
        check=True,
    )

    captured = marker.read_text(encoding="utf-8")
    assert "-m" in captured
    assert "gsigmad" in captured
    assert "--version" in captured
