"""
Tests for governance.fair.fair_check -- FAIR compliance assessment.

Covers FAIR-01 (scored checklist), FAIR-02 (findability),
FAIR-03 (interoperability), FAIR-04 (reusability).

RED phase -- all tests MUST fail until governance/fair/fair_check.py is implemented.
"""
import json
import pytest
from pathlib import Path

from gsigmad.governance.fair.fair_check import (
    run_fair_check,
    check_findable,
    check_accessible,
    check_interoperable,
    check_reusable,
)


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
        "description": "A test experiment for FAIR checks",
        "keywords": ["test", "fair"],
        "creator": "test-agent",
        "identifiers": {},
        "license": "Apache-2.0",
        "methodology": "Standard test methodology",
        "variables": [
            {"name": "temperature", "definition": "Ambient temperature", "unit": "celsius"}
        ],
        "output_files": [],
    }
    record.update(overrides)

    exp_dir = tmp_path / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    safe_id = exp_id.replace("-", "_")
    exp_file = exp_dir / f"{safe_id}_test.json"
    exp_file.write_text(json.dumps(record, indent=2))

    return record


def _make_output_file(tmp_path: Path, filename: str, content=None) -> Path:
    """Create a file at results/{filename} within tmp_path.

    If content is None, writes "placeholder".
    If content is a dict, writes json.dumps(content).
    Returns the Path object.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    fpath = results_dir / filename

    if content is None:
        fpath.write_text("placeholder")
    elif isinstance(content, dict):
        fpath.write_text(json.dumps(content, indent=2))
    else:
        fpath.write_text(str(content))

    return fpath


def _make_prov_json(tmp_path: Path, filename: str = "exp042_provenance.prov.json") -> Path:
    """Create a valid PROV-JSON file at results/{filename}.

    Returns the Path object.
    """
    prov_data = {
        "entity": {},
        "activity": {},
        "wasGeneratedBy": {},
    }
    return _make_output_file(tmp_path, filename, content=prov_data)


def _make_identifiers_json(
    tmp_path: Path,
    exp_id: str = "EXP-042",
    doi: str = None,
    pmid: str = None,
) -> Path:
    """Create .agent/identifiers.json within tmp_path.

    Content: {exp_id: {"doi": doi, "pmid": pmid}} (only include non-None keys).
    Returns the Path object.
    """
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    id_entry = {}
    if doi is not None:
        id_entry["doi"] = doi
    if pmid is not None:
        id_entry["pmid"] = pmid

    data = {exp_id: id_entry}
    fpath = agent_dir / "identifiers.json"
    fpath.write_text(json.dumps(data, indent=2))
    return fpath


# ---------------------------------------------------------------------------
# FAIR-01: run_fair_check orchestrator tests
# ---------------------------------------------------------------------------

class TestRunFairCheck:

    def test_returns_all_four_dimensions(self, tmp_path):
        """run_fair_check returns result with all 4 FAIR dimensions."""
        _make_exp_record(tmp_path)
        result = run_fair_check("EXP-042", str(tmp_path))

        for key in ("exp_id", "checked_at", "dimensions", "total_score", "pass", "summary"):
            assert key in result, f"Expected key '{key}' missing from result"

        assert set(result["dimensions"].keys()) == {
            "findable", "accessible", "interoperable", "reusable"
        }

    def test_total_score_counts_passing_dimensions(self, tmp_path):
        """Full-passing EXP yields total_score == 4 and pass is True."""
        _make_exp_record(
            tmp_path,
            identifiers={"doi": "10.1234/test.2026"},
            license="Apache-2.0",
            methodology="Randomized controlled trial with blinding",
            variables=[
                {"name": "temperature", "definition": "Ambient temperature", "unit": "celsius"}
            ],
            output_files=["results/exp042_data.csv"],
        )
        _make_output_file(tmp_path, "exp042_data.csv", "sample_id,value,unit\n1,42,mg\n")
        _make_prov_json(tmp_path)
        _make_identifiers_json(tmp_path, doi="10.1234/test.2026")

        result = run_fair_check("EXP-042", str(tmp_path))
        assert result["total_score"] == 4
        assert result["pass"] is True

    def test_writes_json_output(self, tmp_path):
        """run_fair_check writes experiments/fair/EXP_042_fair.json."""
        _make_exp_record(tmp_path)
        run_fair_check("EXP-042", str(tmp_path))

        fair_output = tmp_path / "experiments" / "fair" / "EXP_042_fair.json"
        assert fair_output.exists(), f"Expected {fair_output} to be created"

        data = json.loads(fair_output.read_text())
        assert data["exp_id"] == "EXP-042"

    def test_detail_references_specific_files(self, tmp_path):
        """Non-standard format file appears in I-FORMAT sub-check detail."""
        _make_exp_record(
            tmp_path,
            output_files=["results/exp042_raw.xlsx"],
        )
        _make_output_file(tmp_path, "exp042_raw.xlsx")

        result = run_fair_check("EXP-042", str(tmp_path))

        # Find the I-FORMAT sub-check in the interoperable dimension
        i_checks = result["dimensions"]["interoperable"]["sub_checks"]
        i_format = [sc for sc in i_checks if sc["id"] == "I-FORMAT"]
        assert len(i_format) > 0, "I-FORMAT sub-check not found"
        assert "exp042_raw.xlsx" in i_format[0]["detail"]

    def test_creates_output_directory(self, tmp_path):
        """run_fair_check creates experiments/fair/ directory if it does not exist."""
        _make_exp_record(tmp_path)
        # Explicitly do NOT create experiments/fair/ directory
        fair_dir = tmp_path / "experiments" / "fair"
        assert not fair_dir.exists(), "Precondition: fair dir should not exist"

        run_fair_check("EXP-042", str(tmp_path))

        fair_output = tmp_path / "experiments" / "fair" / "EXP_042_fair.json"
        assert fair_output.exists(), "Output JSON should be created despite missing directory"

    def test_missing_exp_record_returns_error(self, tmp_path):
        """Missing EXP record returns pass=False with exp_id in summary."""
        result = run_fair_check("EXP-999", str(tmp_path))
        assert result["pass"] is False
        assert "EXP-999" in result["summary"]


# ---------------------------------------------------------------------------
# FAIR-02: Findability tests
# ---------------------------------------------------------------------------

class TestCheckFindable:

    def test_f_id_doi_in_record(self, tmp_path):
        """DOI in EXP record identifiers passes F-ID."""
        record = _make_exp_record(
            tmp_path,
            identifiers={"doi": "10.1234/test.2026"},
        )
        result = check_findable(record, str(tmp_path))

        f_id = [sc for sc in result["sub_checks"] if sc["id"] == "F-ID"]
        assert len(f_id) > 0, "F-ID sub-check not found"
        assert f_id[0]["pass"] is True
        assert "10.1234/test.2026" in f_id[0]["detail"]

    def test_f_id_doi_in_identifiers_json(self, tmp_path):
        """DOI in .agent/identifiers.json passes F-ID with fallback note."""
        record = _make_exp_record(tmp_path, identifiers={})
        _make_identifiers_json(tmp_path, doi="10.5678/fallback")

        result = check_findable(record, str(tmp_path))

        f_id = [sc for sc in result["sub_checks"] if sc["id"] == "F-ID"]
        assert len(f_id) > 0, "F-ID sub-check not found"
        assert f_id[0]["pass"] is True
        assert "identifiers.json" in f_id[0]["detail"]

    def test_f_id_missing_blocks_pass(self, tmp_path):
        """No persistent identifier anywhere fails F-ID and dimension."""
        record = _make_exp_record(tmp_path, identifiers={})
        result = check_findable(record, str(tmp_path))

        f_id = [sc for sc in result["sub_checks"] if sc["id"] == "F-ID"]
        assert len(f_id) > 0, "F-ID sub-check not found"
        assert f_id[0]["pass"] is False
        assert "No persistent identifier" in f_id[0]["detail"]
        assert result["pass"] is False

    def test_f_meta_all_present(self, tmp_path):
        """All metadata fields present passes F-META."""
        record = _make_exp_record(
            tmp_path,
            title="Full Title",
            description="A detailed description",
            keywords=["test", "fair"],
            creator="test-agent",
        )
        result = check_findable(record, str(tmp_path))

        f_meta = [sc for sc in result["sub_checks"] if sc["id"] == "F-META"]
        assert len(f_meta) > 0, "F-META sub-check not found"
        assert f_meta[0]["pass"] is True

    def test_f_meta_missing_fields(self, tmp_path):
        """Missing description and keywords fails F-META with field names in detail."""
        record = _make_exp_record(
            tmp_path,
            title="Partial Record",
            description="",
            keywords=[],
            creator="test-agent",
        )
        result = check_findable(record, str(tmp_path))

        f_meta = [sc for sc in result["sub_checks"] if sc["id"] == "F-META"]
        assert len(f_meta) > 0, "F-META sub-check not found"
        assert f_meta[0]["pass"] is False
        assert "description" in f_meta[0]["detail"]
        assert "keywords" in f_meta[0]["detail"]


# ---------------------------------------------------------------------------
# FAIR-01 sub-checks: Accessibility tests
# ---------------------------------------------------------------------------

class TestCheckAccessible:

    def test_a_protocol_files_exist(self, tmp_path):
        """All declared output files exist on disk passes A-PROTOCOL."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_data.csv"],
        )
        _make_output_file(tmp_path, "exp042_data.csv", "sample_id,value\n1,42\n")

        result = check_accessible(record, str(tmp_path))

        a_proto = [sc for sc in result["sub_checks"] if sc["id"] == "A-PROTOCOL"]
        assert len(a_proto) > 0, "A-PROTOCOL sub-check not found"
        assert a_proto[0]["pass"] is True

    def test_a_protocol_file_missing(self, tmp_path):
        """Missing declared output file fails A-PROTOCOL with filename in detail."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_missing.csv"],
        )
        # Do NOT create the file

        result = check_accessible(record, str(tmp_path))

        a_proto = [sc for sc in result["sub_checks"] if sc["id"] == "A-PROTOCOL"]
        assert len(a_proto) > 0, "A-PROTOCOL sub-check not found"
        assert a_proto[0]["pass"] is False
        assert "exp042_missing.csv" in a_proto[0]["detail"]

    def test_a_license_from_exp_record(self, tmp_path):
        """License in EXP record passes A-LICENSE."""
        record = _make_exp_record(tmp_path, license="MIT")

        result = check_accessible(record, str(tmp_path))

        a_lic = [sc for sc in result["sub_checks"] if sc["id"] == "A-LICENSE"]
        assert len(a_lic) > 0, "A-LICENSE sub-check not found"
        assert a_lic[0]["pass"] is True
        assert "MIT" in a_lic[0]["detail"]

    def test_a_license_from_file(self, tmp_path):
        """LICENSE file on disk passes A-LICENSE when record has no license field."""
        record = _make_exp_record(tmp_path)
        # Remove license from record
        record.pop("license", None)
        # Re-write the EXP file without license
        exp_file = tmp_path / "experiments" / "EXP_042_test.json"
        exp_file.write_text(json.dumps(record, indent=2))

        license_file = tmp_path / "LICENSE"
        license_file.write_text("MIT License\n\nCopyright (c) 2026 Test\n")

        result = check_accessible(record, str(tmp_path))

        a_lic = [sc for sc in result["sub_checks"] if sc["id"] == "A-LICENSE"]
        assert len(a_lic) > 0, "A-LICENSE sub-check not found"
        assert a_lic[0]["pass"] is True

    def test_a_license_missing(self, tmp_path):
        """No license in record or on disk fails A-LICENSE."""
        record = _make_exp_record(tmp_path)
        record.pop("license", None)
        exp_file = tmp_path / "experiments" / "EXP_042_test.json"
        exp_file.write_text(json.dumps(record, indent=2))

        result = check_accessible(record, str(tmp_path))

        a_lic = [sc for sc in result["sub_checks"] if sc["id"] == "A-LICENSE"]
        assert len(a_lic) > 0, "A-LICENSE sub-check not found"
        assert a_lic[0]["pass"] is False


# ---------------------------------------------------------------------------
# FAIR-03: Interoperability tests
# ---------------------------------------------------------------------------

class TestCheckInteroperable:

    def test_i_format_standard_csv(self, tmp_path):
        """Standard CSV with headers passes I-FORMAT."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_data.csv"],
        )
        _make_output_file(tmp_path, "exp042_data.csv", "sample_id,value,unit\n1,42,mg\n")

        result = check_interoperable(record, str(tmp_path))

        i_fmt = [sc for sc in result["sub_checks"] if sc["id"] == "I-FORMAT"]
        assert len(i_fmt) > 0, "I-FORMAT sub-check not found"
        assert i_fmt[0]["pass"] is True

    def test_i_format_non_standard_flagged(self, tmp_path):
        """Non-standard format (.xlsx) fails I-FORMAT with recommendation."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_raw.xlsx"],
        )
        _make_output_file(tmp_path, "exp042_raw.xlsx")

        result = check_interoperable(record, str(tmp_path))

        i_fmt = [sc for sc in result["sub_checks"] if sc["id"] == "I-FORMAT"]
        assert len(i_fmt) > 0, "I-FORMAT sub-check not found"
        assert i_fmt[0]["pass"] is False
        assert "exp042_raw.xlsx" in i_fmt[0]["detail"]
        # Should recommend a standard format
        detail_lower = i_fmt[0]["detail"].lower()
        assert "csv" in detail_lower or "json" in detail_lower, (
            f"Expected format recommendation in detail, got: {i_fmt[0]['detail']}"
        )

    def test_i_vocab_context_present(self, tmp_path):
        """JSON file with @context passes I-VOCAB."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_data.json"],
        )
        _make_output_file(
            tmp_path,
            "exp042_data.json",
            content={"@context": "https://schema.org", "data": []},
        )

        result = check_interoperable(record, str(tmp_path))

        i_vocab = [sc for sc in result["sub_checks"] if sc["id"] == "I-VOCAB"]
        assert len(i_vocab) > 0, "I-VOCAB sub-check not found"
        assert i_vocab[0]["pass"] is True

    def test_i_vocab_missing(self, tmp_path):
        """JSON without @context and no vocabulary field fails I-VOCAB."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_data.json"],
        )
        _make_output_file(
            tmp_path,
            "exp042_data.json",
            content={"data": [1, 2, 3]},
        )

        result = check_interoperable(record, str(tmp_path))

        i_vocab = [sc for sc in result["sub_checks"] if sc["id"] == "I-VOCAB"]
        assert len(i_vocab) > 0, "I-VOCAB sub-check not found"
        assert i_vocab[0]["pass"] is False

    def test_i_prov_valid(self, tmp_path):
        """Valid PROV-JSON with required keys passes I-PROV."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_provenance.prov.json"],
        )
        _make_prov_json(tmp_path)

        result = check_interoperable(record, str(tmp_path))

        i_prov = [sc for sc in result["sub_checks"] if sc["id"] == "I-PROV"]
        assert len(i_prov) > 0, "I-PROV sub-check not found"
        assert i_prov[0]["pass"] is True

    def test_i_prov_missing_keys(self, tmp_path):
        """PROV-JSON missing activity and wasGeneratedBy fails I-PROV."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_provenance.prov.json"],
        )
        _make_output_file(
            tmp_path,
            "exp042_provenance.prov.json",
            content={"entity": {}},
        )

        result = check_interoperable(record, str(tmp_path))

        i_prov = [sc for sc in result["sub_checks"] if sc["id"] == "I-PROV"]
        assert len(i_prov) > 0, "I-PROV sub-check not found"
        assert i_prov[0]["pass"] is False
        detail = i_prov[0]["detail"]
        assert "activity" in detail or "wasGeneratedBy" in detail

    def test_i_prov_invalid_json(self, tmp_path):
        """Invalid JSON in .prov.json fails I-PROV with 'invalid' in detail."""
        record = _make_exp_record(
            tmp_path,
            output_files=["results/exp042_provenance.prov.json"],
        )
        results_dir = tmp_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        prov_file = results_dir / "exp042_provenance.prov.json"
        prov_file.write_text("not json{")

        result = check_interoperable(record, str(tmp_path))

        i_prov = [sc for sc in result["sub_checks"] if sc["id"] == "I-PROV"]
        assert len(i_prov) > 0, "I-PROV sub-check not found"
        assert i_prov[0]["pass"] is False
        assert "invalid" in i_prov[0]["detail"].lower()


# ---------------------------------------------------------------------------
# FAIR-04: Reusability tests
# ---------------------------------------------------------------------------

class TestCheckReusable:

    def test_r_license_from_record(self, tmp_path):
        """License in EXP record passes R-LICENSE."""
        record = _make_exp_record(tmp_path, license="Apache-2.0")

        result = check_reusable(record, str(tmp_path))

        r_lic = [sc for sc in result["sub_checks"] if sc["id"] == "R-LICENSE"]
        assert len(r_lic) > 0, "R-LICENSE sub-check not found"
        assert r_lic[0]["pass"] is True
        assert "Apache-2.0" in r_lic[0]["detail"]

    def test_r_license_missing(self, tmp_path):
        """No license in record or on disk fails R-LICENSE."""
        record = _make_exp_record(tmp_path)
        record.pop("license", None)
        exp_file = tmp_path / "experiments" / "EXP_042_test.json"
        exp_file.write_text(json.dumps(record, indent=2))

        result = check_reusable(record, str(tmp_path))

        r_lic = [sc for sc in result["sub_checks"] if sc["id"] == "R-LICENSE"]
        assert len(r_lic) > 0, "R-LICENSE sub-check not found"
        assert r_lic[0]["pass"] is False

    def test_r_method_present(self, tmp_path):
        """Non-empty methodology passes R-METHOD."""
        record = _make_exp_record(
            tmp_path,
            methodology="We used a randomized controlled design with double blinding.",
        )

        result = check_reusable(record, str(tmp_path))

        r_method = [sc for sc in result["sub_checks"] if sc["id"] == "R-METHOD"]
        assert len(r_method) > 0, "R-METHOD sub-check not found"
        assert r_method[0]["pass"] is True

    def test_r_method_missing(self, tmp_path):
        """Empty methodology fails R-METHOD."""
        record = _make_exp_record(tmp_path, methodology="")

        result = check_reusable(record, str(tmp_path))

        r_method = [sc for sc in result["sub_checks"] if sc["id"] == "R-METHOD"]
        assert len(r_method) > 0, "R-METHOD sub-check not found"
        assert r_method[0]["pass"] is False

    def test_r_vardef_complete(self, tmp_path):
        """Variable with name, definition, and unit passes R-VARDEF."""
        record = _make_exp_record(
            tmp_path,
            variables=[{"name": "temp", "definition": "Temperature in sample", "unit": "K"}],
        )

        result = check_reusable(record, str(tmp_path))

        r_vardef = [sc for sc in result["sub_checks"] if sc["id"] == "R-VARDEF"]
        assert len(r_vardef) > 0, "R-VARDEF sub-check not found"
        assert r_vardef[0]["pass"] is True

    def test_r_vardef_missing(self, tmp_path):
        """Variable missing definition fails R-VARDEF with variable name in detail."""
        record = _make_exp_record(
            tmp_path,
            variables=[{"name": "conc_ratio", "unit": "dimensionless"}],
        )

        result = check_reusable(record, str(tmp_path))

        r_vardef = [sc for sc in result["sub_checks"] if sc["id"] == "R-VARDEF"]
        assert len(r_vardef) > 0, "R-VARDEF sub-check not found"
        assert r_vardef[0]["pass"] is False
        assert "conc_ratio" in r_vardef[0]["detail"]
        assert "definition" in r_vardef[0]["detail"]

    def test_r_units_missing(self, tmp_path):
        """Variable missing unit fails R-UNITS with variable name in detail."""
        record = _make_exp_record(
            tmp_path,
            variables=[{"name": "pressure", "definition": "Chamber pressure"}],
        )

        result = check_reusable(record, str(tmp_path))

        r_units = [sc for sc in result["sub_checks"] if sc["id"] == "R-UNITS"]
        assert len(r_units) > 0, "R-UNITS sub-check not found"
        assert r_units[0]["pass"] is False
        assert "pressure" in r_units[0]["detail"]
        assert "unit" in r_units[0]["detail"]

    def test_r_no_variables_array(self, tmp_path):
        """Missing variables field entirely fails both R-VARDEF and R-UNITS."""
        record = _make_exp_record(tmp_path)
        record.pop("variables", None)
        exp_file = tmp_path / "experiments" / "EXP_042_test.json"
        exp_file.write_text(json.dumps(record, indent=2))

        result = check_reusable(record, str(tmp_path))

        r_vardef = [sc for sc in result["sub_checks"] if sc["id"] == "R-VARDEF"]
        r_units = [sc for sc in result["sub_checks"] if sc["id"] == "R-UNITS"]

        assert len(r_vardef) > 0, "R-VARDEF sub-check not found"
        assert len(r_units) > 0, "R-UNITS sub-check not found"
        assert r_vardef[0]["pass"] is False
        assert r_units[0]["pass"] is False
