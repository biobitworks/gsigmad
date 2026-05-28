# gsigmad Homebrew Tap Template

This directory is a Homebrew tap template. It is not yet published and is not
install-ready because the formula still needs the real PyPI sdist checksum and
generated Python resource stanzas.

## Current Status

- Status: `deferred_until_pypi_and_resources`
- Do not advertise `brew install` as live until the checklist below passes.
- Local dry-run validation:

```bash
uv run python scripts/homebrew_artifact_smoke.py
```

## Publishing Checklist

1. Publish gsigmad to PyPI: `python -m build && twine upload dist/*`
2. Generate resource stanzas: `pip install homebrew-pypi-poet && poet gsigmad`
3. Update gsigmad.rb with actual URL, sha256, and resource stanzas
4. Create the tap repo: https://github.com/biobitworks/homebrew-gsigmad
5. Copy gsigmad.rb to Formula/ in the tap repo
6. Test: `brew audit --new-formula gsigmad && brew test gsigmad`
