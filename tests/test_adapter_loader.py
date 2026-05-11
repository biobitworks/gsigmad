"""Tests for governance/compiler/adapter_loader.py.

TDD RED: These tests are written before the implementation.
All tests should fail before adapter_loader.py is created.
"""

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_adapter(
    adapters_dir: Path,
    filename: str,
    name: str,
    project_path: Path,
    has_canon: bool,
    namespace_prefix: str,
) -> None:
    adapters_dir.mkdir(parents=True, exist_ok=True)
    adapters_dir.joinpath(filename).write_text(
        "\n".join(
            [
                f"# Adapter: {name}",
                "",
                f"**Path:** {project_path}",
                "",
                f"has_canon: {str(has_canon).lower()}",
                "",
                f"**EXP namespace prefix:** `{namespace_prefix}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Integration tests against the real adapters/ directory
# ---------------------------------------------------------------------------


class TestLoadProjectRegistry:
    """Tests for the load_project_registry() public function."""

    def setup_method(self):
        from gsigmad.governance.compiler.adapter_loader import load_project_registry
        self.load = load_project_registry

    # ------------------------------------------------------------------
    # Test 2: overwatch has has_canon=True
    # ------------------------------------------------------------------
    def test_overwatch_has_canon_true(self, tmp_path: Path):
        """overwatch adapter declares has_canon: true."""
        _write_adapter(tmp_path / "adapters", "overwatch.md", "Overwatch", tmp_path / "overwatch", True, "overwatch:")
        registry = self.load(str(tmp_path))
        by_name = {e["name"]: e for e in registry}
        assert "overwatch" in by_name, "Expected 'overwatch' entry in registry"
        assert by_name["overwatch"]["has_canon"] is True

    # ------------------------------------------------------------------
    # Test 3: conductor has has_canon=False
    # ------------------------------------------------------------------
    def test_conductor_has_canon_false(self, tmp_path: Path):
        """conductor adapter declares has_canon: false."""
        _write_adapter(tmp_path / "adapters", "conductor.md", "Conductor", tmp_path / "conductor", False, "conductor:")
        registry = self.load(str(tmp_path))
        by_name = {e["name"]: e for e in registry}
        assert "conductor" in by_name, "Expected 'conductor' entry in registry"
        assert by_name["conductor"]["has_canon"] is False

    # ------------------------------------------------------------------
    # Test 4: Every entry has all four required keys
    # ------------------------------------------------------------------
    def test_all_entries_have_required_keys(self, tmp_path: Path):
        """Each dict must have name, canon_path, has_canon, namespace_prefix."""
        _write_adapter(tmp_path / "adapters", "alpha.md", "Alpha", tmp_path / "alpha", True, "alpha:")
        _write_adapter(tmp_path / "adapters", "beta.md", "Beta", tmp_path / "beta", False, "beta:")
        registry = self.load(str(tmp_path))
        required_keys = {"name", "canon_path", "has_canon", "namespace_prefix"}
        for entry in registry:
            missing = required_keys - set(entry.keys())
            assert not missing, (
                f"Entry '{entry.get('name', '?')}' is missing keys: {missing}"
            )

    # ------------------------------------------------------------------
    # Test 5: canon_path for overwatch ends with overwatch/CANON.md
    # ------------------------------------------------------------------
    def test_overwatch_canon_path_ends_correctly(self, tmp_path: Path):
        """overwatch canon_path must end with 'overwatch/CANON.md'."""
        _write_adapter(tmp_path / "adapters", "overwatch.md", "Overwatch", tmp_path / "overwatch", True, "overwatch:")
        registry = self.load(str(tmp_path))
        by_name = {e["name"]: e for e in registry}
        canon_path = by_name["overwatch"]["canon_path"]
        assert canon_path.endswith("overwatch/CANON.md"), (
            f"Expected canon_path to end with 'overwatch/CANON.md', got: {canon_path}"
        )

    # ------------------------------------------------------------------
    # Test 6: Result is sorted by name
    # ------------------------------------------------------------------
    def test_registry_sorted_by_name(self, tmp_path: Path):
        """Registry must be sorted alphabetically by name."""
        _write_adapter(tmp_path / "adapters", "zeta.md", "Zeta", tmp_path / "zeta", True, "zeta:")
        _write_adapter(tmp_path / "adapters", "alpha.md", "Alpha", tmp_path / "alpha", True, "alpha:")
        registry = self.load(str(tmp_path))
        names = [e["name"] for e in registry]
        assert names == sorted(names), (
            f"Registry not sorted by name. Got: {names}"
        )


# ---------------------------------------------------------------------------
# Error-handling tests (using real adapter files to validate ValueError paths)
# ---------------------------------------------------------------------------

class TestAdapterLoaderErrors:
    """Tests for ValueError raised on malformed adapter files."""

    def setup_method(self):
        from gsigmad.governance.compiler.adapter_loader import load_project_registry
        self.load = load_project_registry

    def test_missing_path_field_raises_valueerror(self, tmp_path):
        """Adapter missing **Path:** must raise ValueError with filename in message."""
        bad_adapter = tmp_path / "bad-project.md"
        bad_adapter.write_text(
            "# Adapter: Bad Project\n\nhas_canon: false\n\n**EXP namespace prefix:** `bad:`\n"
        )
        with pytest.raises(ValueError, match="bad-project.md"):
            self.load(str(tmp_path), adapters_dir=".")

    def test_missing_has_canon_raises_valueerror(self, tmp_path):
        """Adapter missing has_canon line must raise ValueError with filename in message."""
        bad_adapter = tmp_path / "incomplete-project.md"
        bad_adapter.write_text(
            "# Adapter: Incomplete Project\n\n**Path:** /some/path/\n\n**EXP namespace prefix:** `incomplete:`\n"
        )
        with pytest.raises(ValueError, match="incomplete-project.md"):
            self.load(str(tmp_path), adapters_dir=".")
