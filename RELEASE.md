# Public Release Checklist

Release target: `gsigmad` public GitHub repository.

## 1.2.0b1 Public Beta Candidate

`1.2.0b1` is a public beta candidate for GitHub and Hugging Face dry-run
surfaces. It keeps Homebrew, DOI/Zenodo, ratified benchmark wording,
FIGURE-### writeback, and any truth-validation claims explicitly deferred.

Allowed release wording:

- local-first science governance CLI and Agent Skills bundle
- deterministic guardrails around probabilistic AI workflows
- synthetic public benchmark seed corpus
- deterministic gate-boundary demo
- missing integrations are `not_configured`, never PASS

Do not describe this release as stable, truth-validating, a ratified benchmark,
or a replacement for OSF, Galaxy, WorkflowHub, MLflow, ELNs, or workflow
engines.

## Release Notes Template (use verbatim at tag time)

```
gsigmad 1.2.0b1 - public beta release candidate.

What's in it
- Local-first science governance CLI and Agent Skills bundle for AI-assisted
  research workflows.
- Deterministic gates against the represented public beta gate surface
  (see docs/CAPABILITY_MATRIX.md): h1_completeness, evidence_class_guardrail,
  reproducibility_declaration, citation_resolution, data_contract, manifest
  presence (advisory), drift scan (advisory), adapter resolution (never PASS
  when missing).
- Hugging Face demo dataset card and static Space dry-run bundles.
- Public benchmark seed corpus and failure taxonomy.

What's deferred
- Homebrew: deferred_until_pypi_and_resources.
- Ratified benchmark wording: deferred until PI ratification.
- Figure writeback: figures rendered by gsigmad-figure-create stay
  figure_destination=local_only; writeback to overwatch_evidence /
  seedgraph_document is deferred.

What's prohibited
- "validates scientific truth"
- "catches all scientific misconduct"
- "replaces OSF / Galaxy / Renku / WorkflowHub / Arvados / MLflow / W&B / [any
  ELN] / [any workflow engine]"
- "stable" applied to this release

Citation
gsigmad 1.2.0b1 - Biobitworks. DOI: pending Zenodo archive of this release.
```

Do not introduce a placeholder DOI, "10.xxxx" string, or any pseudo-identifier
that could be read as a real DOI.

## Included

- `src/gsigmad/` Python package
- `skills/gsigmad*/SKILL.md` source skills
- packaged skill bundle under `src/gsigmad/skill_bundle/skills/`
- public docs, specs, tests, npm shim, Homebrew formula
- generic adapter examples only

## Excluded

- private planning state
- private project adapters
- experiment run records
- raw data
- local receipts
- dashboards and operator-only exports
- live database, KG, or writeback configuration
- caches, virtualenvs, generated artifacts, and worktrees

## Release Gate

Before pushing publicly:

- tests pass
- secret scan has no confirmed credential leaks
- private-surface scan has no internal-only directories
- package metadata includes license, citation, security, and contribution files
- GitHub remote is explicitly configured for the intended public repo

The private upstream development repo ships an executable release-gate scan
that enforces the above. From that upstream checkout:

```bash
python3 scripts/release_gate_scan.py /path/to/gsigmad
pytest tests/test_release_gate.py -q
```

Exit code 1 on any BLOCK-class finding halts the release. The scan
rules are committed at
`.planning/quick/260511-gsigmad-public-release-ip-redteam/SANITIZATION-RULES.json`.
