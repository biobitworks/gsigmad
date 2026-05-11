"""
Tests for governance.export -- publication bundle assembly and repository upload.

Covers PUB-01 (manifest generation), PUB-02 (bundle contents),
PUB-03 (OSF integration), PUB-04 (Zenodo integration).

RED phase -- all tests MUST fail until governance/export/exporter.py,
governance/export/osf_client.py, and governance/export/zenodo_client.py
are implemented.
"""
import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gsigmad.governance.export.exporter import create_bundle
from gsigmad.governance.export.osf_client import upload_to_osf
from gsigmad.governance.export.zenodo_client import deposit_to_zenodo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exp_record(tmp_path: Path, exp_id: str = "EXP-042", **overrides) -> dict:
    """Create a minimal EXP JSON file at experiments/EXP_042_test.json.

    Returns the record dict.
    """
    record = {
        "exp_id": exp_id,
        "title": "Test Experiment",
        "description": "A test experiment for export checks",
        "keywords": ["test", "export"],
        "creator": "test-agent",
        "license": "Apache-2.0",
        "methodology": "Standard test methodology",
        "variables": [
            {"name": "temperature", "definition": "Ambient temperature", "unit": "celsius"}
        ],
        "output_files": ["results/exp042_data.csv"],
        "scripts": ["scripts/analyze.py"],
    }
    record.update(overrides)

    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    safe_id = exp_id.replace("-", "_")
    exp_file = exp_dir / f"{safe_id}_test.json"
    exp_file.write_text(json.dumps(record, indent=2))

    return record


def _make_bundle_fixtures(tmp_path: Path, exp_id: str = "EXP-042") -> dict:
    """Create all 6 artifact types for a complete export bundle.

    Returns the EXP record dict.
    """
    record = _make_exp_record(tmp_path, exp_id)

    # 1. Data file (CSV with headers)
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_file = results_dir / "exp042_data.csv"
    csv_file.write_text("sample_id,value,unit\n1,42,mg\n2,84,mg\n")

    # 2. Analysis script
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_file = scripts_dir / "analyze.py"
    script_file.write_text("# Analysis script for EXP-042\nimport pandas as pd\n")

    # 3. Pre-registration document
    pre_reg_dir = tmp_path / "experiments" / "pre-reg"
    pre_reg_dir.mkdir(parents=True, exist_ok=True)
    pre_reg_file = pre_reg_dir / "EXP_042_pre_reg.md"
    pre_reg_file.write_text("# Pre-Registration: EXP-042\n\n## Hypothesis\nTest hypothesis.\n")

    # 4. FAIR assessment JSON
    fair_dir = tmp_path / "experiments" / "fair"
    fair_dir.mkdir(parents=True, exist_ok=True)
    fair_file = fair_dir / "EXP_042_fair.json"
    fair_data = {
        "exp_id": exp_id,
        "total_score": 3,
        "pass": True,
        "dimensions": {"findable": {"pass": True}, "accessible": {"pass": True},
                       "interoperable": {"pass": True}, "reusable": {"pass": False}},
    }
    fair_file.write_text(json.dumps(fair_data, indent=2))

    # 5. PROV-JSON provenance file
    prov_file = results_dir / "exp042.prov.json"
    prov_data = {
        "entity": {"ex:data1": {"prov:type": "prov:Collection"}},
        "activity": {"ex:run1": {"prov:type": "prov:Activity"}},
        "wasGeneratedBy": {"ex:data1": {"prov:activity": "ex:run1"}},
    }
    prov_file.write_text(json.dumps(prov_data, indent=2))

    # 6. Lab notebook with EXP-042 entry
    notebook_file = tmp_path / "LAB_NOTEBOOK.md"
    notebook_file.write_text(
        "# Lab Notebook\n\n"
        "## 2026-04-01 EXP-042 Initial Run\n\n"
        "Ran experiment EXP-042 with standard parameters.\n"
        "Results saved to results/exp042_data.csv.\n\n"
        "---\n\n"
        "## 2026-03-30 EXP-041 Setup\n\n"
        "Unrelated entry for EXP-041.\n"
    )

    return record


# ---------------------------------------------------------------------------
# PUB-01: create_bundle core tests
# ---------------------------------------------------------------------------

class TestCreateBundle:
    """Tests for create_bundle() directory and manifest creation."""

    def test_creates_bundle_directory(self, tmp_path):
        """create_bundle creates exports/EXP-042/ directory."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        assert Path(bundle_path).is_dir()
        assert "EXP-042" in bundle_path

    def test_manifest_json_exists(self, tmp_path):
        """manifest.json exists in the bundle directory."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        manifest_path = Path(bundle_path) / "manifest.json"
        assert manifest_path.exists()

    def test_manifest_has_exp_id(self, tmp_path):
        """manifest['exp_id'] == 'EXP-042'."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        assert manifest["exp_id"] == "EXP-042"

    def test_manifest_has_created_at(self, tmp_path):
        """manifest['created_at'] is an ISO 8601 string."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        created_at = manifest["created_at"]
        assert isinstance(created_at, str)
        # Basic ISO 8601 check: contains 'T' and ends with 'Z' or has timezone
        assert "T" in created_at

    def test_returns_tuple(self, tmp_path):
        """create_bundle returns (bundle_path: str, manifest: dict)."""
        _make_bundle_fixtures(tmp_path)
        result = create_bundle("EXP-042", gsd_root=str(tmp_path))
        assert isinstance(result, tuple)
        assert len(result) == 2
        bundle_path, manifest = result
        assert isinstance(bundle_path, str)
        assert isinstance(manifest, dict)


# ---------------------------------------------------------------------------
# PUB-01: Manifest field tests
# ---------------------------------------------------------------------------

class TestManifestFields:
    """Tests for manifest.json field requirements."""

    def test_sha256_checksum_present(self, tmp_path):
        """Each artifact entry with status 'present' has a 64-char hex sha256."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        for artifact in manifest["artifacts"]:
            if artifact.get("status") == "present":
                sha = artifact["sha256"]
                assert isinstance(sha, str) and len(sha) == 64, (
                    f"Expected 64-char hex sha256, got: {sha!r}"
                )

    def test_artifact_type_field(self, tmp_path):
        """Each entry has artifact_type in the expected set."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        valid_types = {"data", "script", "pre-reg", "notebook", "provenance", "fair"}
        for artifact in manifest["artifacts"]:
            assert artifact["artifact_type"] in valid_types, (
                f"Unexpected artifact_type: {artifact['artifact_type']}"
            )

    def test_prov_json_hash_for_provenance(self, tmp_path):
        """Provenance entries have prov_json_hash set."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        prov_entries = [a for a in manifest["artifacts"] if a["artifact_type"] == "provenance"]
        assert len(prov_entries) > 0, "Expected at least one provenance artifact"
        for entry in prov_entries:
            assert entry.get("prov_json_hash") is not None, (
                "provenance entry missing prov_json_hash"
            )

    def test_fair_score_for_fair_artifact(self, tmp_path):
        """FAIR entries have fair_score set (from FAIR JSON total_score)."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        fair_entries = [a for a in manifest["artifacts"] if a["artifact_type"] == "fair"]
        assert len(fair_entries) > 0, "Expected at least one fair artifact"
        for entry in fair_entries:
            assert entry.get("fair_score") is not None, (
                "fair entry missing fair_score"
            )


# ---------------------------------------------------------------------------
# PUB-02: Bundle contents tests
# ---------------------------------------------------------------------------

class TestBundleContents:
    """Tests for files included in the export bundle."""

    def test_data_files_included(self, tmp_path):
        """CSV data files from results/ are copied into bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        data_files = list(bundle_dir.glob("**/*.csv"))
        assert len(data_files) > 0, "Expected CSV data files in bundle"

    def test_scripts_included(self, tmp_path):
        """Analysis scripts referenced in EXP record are copied."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        script_files = list(bundle_dir.glob("**/*.py"))
        assert len(script_files) > 0, "Expected analysis scripts in bundle"

    def test_pre_reg_included(self, tmp_path):
        """Pre-registration document is copied into bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        pre_reg_files = list(bundle_dir.glob("**/*pre_reg*"))
        assert len(pre_reg_files) > 0, "Expected pre-registration document in bundle"

    def test_notebook_excerpt_included(self, tmp_path):
        """Lab notebook excerpt file is created in bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        notebook_files = list(bundle_dir.glob("**/*notebook*"))
        assert len(notebook_files) > 0, "Expected lab notebook excerpt in bundle"

    def test_provenance_included(self, tmp_path):
        """PROV-JSON files are copied into bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        prov_files = list(bundle_dir.glob("**/*.prov.json"))
        assert len(prov_files) > 0, "Expected PROV-JSON file in bundle"

    def test_fair_assessment_included(self, tmp_path):
        """FAIR assessment JSON is copied into bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        bundle_dir = Path(bundle_path)
        fair_files = list(bundle_dir.glob("**/*fair*"))
        assert len(fair_files) > 0, "Expected FAIR assessment JSON in bundle"


# ---------------------------------------------------------------------------
# PUB-02: Missing artifacts tests
# ---------------------------------------------------------------------------

class TestMissingArtifacts:
    """Tests for graceful handling of missing source artifacts."""

    def test_missing_artifact_status(self, tmp_path):
        """When a source file does not exist, manifest entry has status 'missing' (D-04)."""
        _make_exp_record(tmp_path, output_files=["results/nonexistent.csv"])
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        missing = [a for a in manifest["artifacts"] if a.get("status") == "missing"]
        assert len(missing) > 0, "Expected at least one artifact with status 'missing'"

    def test_export_completes_with_missing(self, tmp_path):
        """create_bundle succeeds even when artifacts are missing (D-04)."""
        _make_exp_record(tmp_path, output_files=["results/nonexistent.csv"])
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        assert Path(bundle_path).is_dir()
        assert manifest["exp_id"] == "EXP-042"

    def test_missing_sha256_is_none(self, tmp_path):
        """Missing artifact entries have sha256 as None."""
        _make_exp_record(tmp_path, output_files=["results/nonexistent.csv"])
        bundle_path, manifest = create_bundle("EXP-042", gsd_root=str(tmp_path))
        missing = [a for a in manifest["artifacts"] if a.get("status") == "missing"]
        for entry in missing:
            assert entry.get("sha256") is None, (
                f"Missing artifact should have sha256=None, got {entry.get('sha256')}"
            )


# ---------------------------------------------------------------------------
# PUB-03: OSF upload tests
# ---------------------------------------------------------------------------

class TestOSFUpload:
    """Tests for upload_to_osf() with mocked requests (D-09)."""

    @patch("gsigmad.governance.export.osf_client.requests")
    def test_upload_creates_component(self, mock_requests, tmp_path):
        """With mocked requests, upload_to_osf creates an OSF component via POST."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        # Mock POST response for component creation
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "data": {
                "id": "abc12",
                "links": {"html": "https://osf.io/abc12/"},
                "relationships": {"files": {"links": {"related": {"href": "https://files.osf.io/v1/resources/abc12/providers/osfstorage/"}}}},
            }
        }
        mock_requests.post.return_value = mock_post_resp

        # Mock PUT response for file uploads
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = upload_to_osf(bundle_path, osf_token="test-token-123")
        mock_requests.post.assert_called()

    @patch("gsigmad.governance.export.osf_client.requests")
    def test_upload_returns_osf_url(self, mock_requests, tmp_path):
        """Result dict contains 'osf_url' key with https://osf.io/ prefix."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "data": {
                "id": "abc12",
                "links": {"html": "https://osf.io/abc12/"},
                "relationships": {"files": {"links": {"related": {"href": "https://files.osf.io/v1/resources/abc12/providers/osfstorage/"}}}},
            }
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = upload_to_osf(bundle_path, osf_token="test-token-123")
        assert "osf_url" in result
        assert result["osf_url"].startswith("https://osf.io/")

    @patch("gsigmad.governance.export.osf_client.requests")
    def test_upload_sends_all_files(self, mock_requests, tmp_path):
        """Mocked PUT called once per file in bundle."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "data": {
                "id": "abc12",
                "links": {"html": "https://osf.io/abc12/"},
                "relationships": {"files": {"links": {"related": {"href": "https://files.osf.io/v1/resources/abc12/providers/osfstorage/"}}}},
            }
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = upload_to_osf(bundle_path, osf_token="test-token-123")
        # Should have at least one PUT call per file in the bundle
        bundle_files = [f for f in Path(bundle_path).iterdir() if f.is_file()]
        assert mock_requests.put.call_count >= len(bundle_files)

    @patch("gsigmad.governance.export.osf_client.requests")
    def test_upload_uses_json_api_content_type(self, mock_requests, tmp_path):
        """POST headers include 'application/vnd.api+json' (Pitfall 1)."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "data": {
                "id": "abc12",
                "links": {"html": "https://osf.io/abc12/"},
                "relationships": {"files": {"links": {"related": {"href": "https://files.osf.io/v1/resources/abc12/providers/osfstorage/"}}}},
            }
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = upload_to_osf(bundle_path, osf_token="test-token-123")
        # Check that the POST call used JSON:API content type
        post_call_kwargs = mock_requests.post.call_args
        headers = post_call_kwargs.kwargs.get("headers", {}) if post_call_kwargs.kwargs else {}
        if not headers and post_call_kwargs.args and len(post_call_kwargs.args) > 1:
            headers = post_call_kwargs.args[1] if isinstance(post_call_kwargs.args[1], dict) else {}
        assert "application/vnd.api+json" in str(headers), (
            f"Expected JSON:API content type in POST headers, got: {headers}"
        )


# ---------------------------------------------------------------------------
# PUB-03: OSF token missing tests
# ---------------------------------------------------------------------------

class TestOSFTokenMissing:
    """Tests for upload_to_osf() with no token configured."""

    def test_missing_token_raises_value_error(self, tmp_path):
        """upload_to_osf with no token env var and no .agent/osf_token raises ValueError."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        # Ensure no token in env or on disk
        env = os.environ.copy()
        env.pop("OSF_TOKEN", None)
        agent_token = Path(bundle_path).parent / ".agent" / "osf_token"
        if agent_token.exists():
            agent_token.unlink()

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                upload_to_osf(bundle_path, osf_token=None)

    def test_error_message_includes_setup_url(self, tmp_path):
        """Error message contains 'https://osf.io/settings/tokens/' (D-07)."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match=r"https://osf\.io/settings/tokens/"):
                upload_to_osf(bundle_path, osf_token=None)


# ---------------------------------------------------------------------------
# PUB-04: Zenodo deposit tests
# ---------------------------------------------------------------------------

class TestZenodoDeposit:
    """Tests for deposit_to_zenodo() with mocked requests (D-13)."""

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_deposit_creates_deposition(self, mock_requests, tmp_path):
        """With mocked requests, deposit_to_zenodo creates a deposit via POST."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        # Mock POST response for deposit creation
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        # Mock PUT responses for file uploads and metadata
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        mock_requests.post.assert_called()

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_deposit_returns_doi(self, mock_requests, tmp_path):
        """Result dict contains 'doi' key."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        assert "doi" in result

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_deposit_returns_deposit_id(self, mock_requests, tmp_path):
        """Result dict contains 'deposit_id' key (int)."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        assert "deposit_id" in result
        assert isinstance(result["deposit_id"], int)

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_deposit_uploads_all_files(self, mock_requests, tmp_path):
        """Mocked PUT called once per file to bucket URL."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        bundle_files = [f for f in Path(bundle_path).iterdir() if f.is_file()]
        # PUT for files + PUT for metadata
        assert mock_requests.put.call_count >= len(bundle_files)

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_deposit_does_not_publish(self, mock_requests, tmp_path):
        """Mocked requests does NOT receive a POST to /actions/publish."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        # Check that no POST call was made to a publish endpoint
        for call in mock_requests.post.call_args_list:
            url = call.args[0] if call.args else call.kwargs.get("url", "")
            assert "actions/publish" not in str(url), (
                "deposit_to_zenodo should NOT auto-publish"
            )


# ---------------------------------------------------------------------------
# PUB-04: Zenodo metadata mapping tests
# ---------------------------------------------------------------------------

class TestZenodoMetadata:
    """Tests for Zenodo metadata mapping from EXP record."""

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_metadata_has_upload_type(self, mock_requests, tmp_path):
        """Mapped metadata includes upload_type 'dataset' (D-12)."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        # The metadata PUT should include upload_type "dataset"
        put_calls = mock_requests.put.call_args_list
        metadata_put = None
        for call in put_calls:
            kwargs = call.kwargs if call.kwargs else {}
            if "json" in kwargs or "data" in kwargs:
                metadata_put = kwargs
                break
        assert metadata_put is not None, "Expected a PUT call with metadata JSON"

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_metadata_has_title(self, mock_requests, tmp_path):
        """Mapped metadata includes title from EXP record."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        # Check metadata was sent with title
        put_calls = mock_requests.put.call_args_list
        found_title = False
        for call in put_calls:
            kwargs = call.kwargs if call.kwargs else {}
            json_data = kwargs.get("json", {})
            if isinstance(json_data, dict) and "metadata" in json_data:
                if "title" in json_data["metadata"]:
                    found_title = True
                    break
        assert found_title, "Expected metadata PUT to include title"

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_metadata_has_creators(self, mock_requests, tmp_path):
        """Mapped metadata includes creators array with name field."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        put_calls = mock_requests.put.call_args_list
        found_creators = False
        for call in put_calls:
            kwargs = call.kwargs if call.kwargs else {}
            json_data = kwargs.get("json", {})
            if isinstance(json_data, dict) and "metadata" in json_data:
                creators = json_data["metadata"].get("creators", [])
                if creators and isinstance(creators, list) and "name" in creators[0]:
                    found_creators = True
                    break
        assert found_creators, "Expected metadata PUT to include creators with name"

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_metadata_has_prereserve_doi(self, mock_requests, tmp_path):
        """Metadata PUT includes prereserve_doi: true."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        put_calls = mock_requests.put.call_args_list
        found_prereserve = False
        for call in put_calls:
            kwargs = call.kwargs if call.kwargs else {}
            json_data = kwargs.get("json", {})
            if isinstance(json_data, dict) and "metadata" in json_data:
                if json_data["metadata"].get("prereserve_doi") is True:
                    found_prereserve = True
                    break
        assert found_prereserve, "Expected metadata PUT to include prereserve_doi: true"

    @patch("gsigmad.governance.export.zenodo_client.requests")
    def test_metadata_has_access_right(self, mock_requests, tmp_path):
        """Mapped metadata includes access_right 'open'."""
        _make_bundle_fixtures(tmp_path)
        bundle_path, _ = create_bundle("EXP-042", gsd_root=str(tmp_path))

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {
            "id": 123456,
            "metadata": {"prereserve_doi": {"doi": "10.5281/zenodo.123456"}},
            "links": {"bucket": "https://zenodo.org/api/files/bucket-id"},
        }
        mock_requests.post.return_value = mock_post_resp

        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 200
        mock_requests.put.return_value = mock_put_resp

        result = deposit_to_zenodo(bundle_path, zenodo_token="test-token-456")
        put_calls = mock_requests.put.call_args_list
        found_access = False
        for call in put_calls:
            kwargs = call.kwargs if call.kwargs else {}
            json_data = kwargs.get("json", {})
            if isinstance(json_data, dict) and "metadata" in json_data:
                if json_data["metadata"].get("access_right") == "open":
                    found_access = True
                    break
        assert found_access, "Expected metadata PUT to include access_right 'open'"
