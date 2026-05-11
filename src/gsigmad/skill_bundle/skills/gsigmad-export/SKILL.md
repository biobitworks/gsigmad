---
name: gsigmad-export
description: "Package experiment artifacts into a submission-ready export bundle with manifest, SHA-256 checksums, and provenance metadata. Optionally upload to OSF or deposit to Zenodo for DOI reservation."
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# Publication Export

Package experiment artifacts into a submission-ready export bundle, then optionally deposit to OSF or Zenodo.

## 1. Pre-Conditions

Before beginning the export:

1. Identify the target EXP-### from the operator's request (e.g., `EXP-042`).
2. Confirm the experiment record exists: check for `experiments/EXP_{NNN}_*.json` where NNN is the numeric part of the EXP ID.
3. If no EXP record is found, STOP and report: "EXP-### not found. Create the experiment record before running export."
4. If `--target osf` flag is specified:
   - Confirm `OSF_TOKEN` environment variable is set or `.agent/osf_token` file exists.
   - Confirm `.agent/osf_config.json` exists and contains a `project_id` field.
   - If either is missing, STOP and report with setup instructions.
5. If `--target zenodo` flag is specified:
   - Confirm `ZENODO_TOKEN` environment variable is set or `.agent/zenodo_token` file exists.
   - If missing, STOP and report with setup instructions.

## 2. Create Export Bundle

Assemble the export bundle using the governance module:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.export.exporter import create_bundle

bundle_path, manifest = create_bundle(exp_id="$ARGUMENTS.exp_id", gsd_root=".")

artifact_count = len(manifest["artifacts"])
missing_count = sum(1 for a in manifest["artifacts"] if a.get("status") == "missing")
present_count = artifact_count - missing_count

print(f"Bundle created at: {bundle_path}")
print(f"Artifacts: {present_count} present, {missing_count} missing, {artifact_count} total")
```

What the module does:

- Loads the EXP record and discovers artifacts from `results/`, `experiments/`, `experiments/fair/`, and `experiments/pre-reg/`.
- Collects 6 artifact types: data files, analysis scripts, pre-registration document, lab notebook excerpts, PROV-JSON provenance chain, and FAIR assessment JSON.
- Copies each artifact into `exports/EXP-###/`, computes SHA-256 checksums on the copies.
- Writes `manifest.json` with per-file `sha256`, `artifact_type`, `exp_id`, `prov_json_hash`, and `fair_score`.
- Missing artifacts get `status: "missing"` entries without halting the export.

## 3. Upload to Repository (Optional)

If `--target osf` was specified, upload the bundle to OSF:

```python
from gsigmad.governance.export.osf_client import upload_to_osf

result = upload_to_osf(bundle_path)

if result["pass"]:
    print(f"Uploaded to OSF: {result['osf_url']}")
else:
    print(f"OSF upload failed: {result['error']}")
```

If `--target zenodo` was specified, deposit the bundle to Zenodo:

```python
from gsigmad.governance.export.zenodo_client import deposit_to_zenodo

result = deposit_to_zenodo(bundle_path)

if result["pass"]:
    print(f"Deposited to Zenodo. Reserved DOI: {result['doi']}")
    print(f"Deposit ID: {result['deposit_id']}")
else:
    print(f"Zenodo deposit failed: {result['error']}")
```

If no `--target` flag was specified, skip the upload step and report that the bundle is ready for manual submission.

## 4. Report Back

Display the export results as a markdown summary table:

| Artifact | Type | Status | SHA-256 (first 12) |
|----------|------|--------|---------------------|
| {filename} | {artifact_type} | {present/missing} | {sha256[:12] or "n/a"} |
| ... | ... | ... | ... |

If an upload was performed:
- **OSF:** Report the component URL (e.g., `https://osf.io/abc12/`)
- **Zenodo:** Report the reserved DOI (e.g., `10.5281/zenodo.123456`) and deposit ID

If any artifacts are missing, list them as action items:
- [ ] {filename}: {artifact_type} artifact is missing -- create or add it before final submission

Report:
- Bundle path: `exports/EXP-###/`
- Manifest: `exports/EXP-###/manifest.json`
- Artifacts: `{present}/{total}` present
- Upload: `{OSF URL or Zenodo DOI or "not uploaded"}`

## 5. Post-Conditions

After the export completes, verify:

1. `exports/EXP-###/manifest.json` exists on disk and is valid JSON.
2. All artifacts with `status: "present"` have a non-null 64-character hex `sha256` value.
3. If upload was performed, the result dict has `"pass": True`.

## Anti-Patterns

**Do NOT auto-publish to Zenodo.** The `deposit_to_zenodo()` function reserves a DOI but does NOT call the publish action. Publishing is a separate, deliberate step the researcher takes after reviewing the deposit on Zenodo's web interface.

**Do NOT skip missing artifacts.** Missing source files are recorded in the manifest with `status: "missing"` and `sha256: null`. The export completes successfully -- it is the operator's responsibility to address gaps before final submission.

**Do NOT hardcode WaterButler URLs for OSF uploads.** The OSF client follows HATEOAS: it reads the upload link from the component's files relationship in the API response, not from a hardcoded URL pattern.
