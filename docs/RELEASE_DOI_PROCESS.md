# Release and DOI Process

This process is for public `gsigmad` releases. It does not publish private
planning state, raw data, private adapters, or live database receipts.

## Release Candidate Gate

Before creating a public release candidate:

```bash
uv sync --all-extras
uv run pytest -q
uv run python scripts/release_smoke.py
uv run python scripts/clean_install_smoke.py
uv run python scripts/npm_package_smoke.py
python -m gsigmad --help
node npm/bin/gsigmad.js --version
```

The upstream release gate must also report zero sanitizer findings against the
public mirror:

```bash
python scripts/release_gate_scan.py /path/to/gsigmad
```

## GitHub Release

1. Confirm `pyproject.toml`, `npm/package.json`, docs, release notes, and tag
   name use the same version.
2. Confirm `CITATION.cff` has the current version and release date.
3. Create a signed tag from the exact commit that passed release smoke.
4. Draft a GitHub release from that tag.
5. Attach or link the release-smoke receipt and package build evidence.
6. State the public claim boundary in the release notes:
   - deterministic guardrails for the current gate set
   - no scientific truth validation
   - no default writeback to external science databases
   - missing adapters are `not_configured`, never PASS

## Zenodo DOI

Zenodo can archive GitHub software releases through its GitHub integration.
After the first public release is archived and a DOI is minted:

1. Record the version DOI in the release notes.
2. Add the DOI to `CITATION.cff` in the next documentation update.
3. Keep the DOI wording precise: cite the archived software release, not a
   peer-reviewed paper or validated benchmark.
4. Do not upload private planning state, private adapters, raw research data, or
   full non-ratified benchmark artifacts to Zenodo.

Until a DOI exists, `CITATION.cff` should remain DOI-free rather than using a
placeholder.

## Hugging Face Release Surfaces

Hugging Face dataset cards and Spaces are appropriate for public examples and
demo traces. They are not the canonical governance truth.

Use Hugging Face for:

- synthetic gate-trace examples
- public claim-boundary corpora
- static demo Spaces that explain deterministic vs creative boundaries

Do not use Hugging Face for:

- raw restricted data
- unpublished private fixtures
- canonical lab notebooks
- live writeback receipts
- claims that the demo proves scientific truth

## Sources

- GitHub CITATION files: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files
- Zenodo GitHub integration: https://help.zenodo.org/docs/github/
- Hugging Face dataset cards: https://huggingface.co/docs/hub/datasets-cards
- Hugging Face static Spaces: https://huggingface.co/docs/hub/main/spaces-sdks-static
