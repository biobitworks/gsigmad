---
name: gsigmad-license-gate
description: "Fail-closed license verification for private/public project pushes and publication promotion. Enforces the portfolio CC BY-NC-ND 4.0 default while preserving upstream licenses and explicit exceptions."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-license-gate

Use before substantive pushes, PR promotion, public release, publication packaging, or source ingestion that may later be redistributed.

Canonical policy:

`docs/PORTFOLIO_LICENSE_POLICY.md`

Default owned-material license:

`CC-BY-NC-ND-4.0`

## Inputs

- repository root
- target branch/destination (`private`, `public`, `release`)
- changed-file list
- repo license file(s)
- source/license registry
- FCO/FCG manifests when present
- exception registry when present
- NOTICE/attribution files
- generated/model-agent provenance records

## Required checks

1. Confirm repository identity and destination.
2. Confirm the current portfolio license policy version.
3. For newly authored owned material, require `CC-BY-NC-ND-4.0` or an explicit exception.
4. For imported/third-party material, preserve the upstream license; never overwrite it with the portfolio default.
5. Require a license status for every atom/source used in a public claim or public artifact.
6. Treat unknown license as `LICENSE_STATUS=UNRESOLVED`.
7. Preserve attribution, copyright, patent, trademark, NOTICE, and other required notices.
8. Detect files whose upstream terms forbid the planned redistribution/transformation.
9. Check that AI/model/agent provenance is recorded separately from license ownership/authority.
10. Check for secrets, private keys, restricted/private source material, or internal-only artifacts before public promotion.
11. Emit an exceptions list with object/path, alternative license, authority, and reason.
12. Emit a deterministic receipt binding policy version, branch, commit/tree identity when available, changed paths, verdict, and blocking codes.

## Verdicts

### PASS

All included objects have resolved license state and the destination is permitted.

### PASS_WITH_EXCEPTIONS

Explicit exceptions exist, are scoped, and do not violate upstream terms. For private repositories, objects may remain internal-only with `PUBLIC_PROMOTION_BLOCKED=true`.

### BLOCK

Block when any of the following is true:

- missing repository/object license state;
- unresolved third-party license intended for public redistribution;
- attempted silent relicensing of upstream material;
- planned redistribution of adapted material where derivatives may not be shared;
- planned commercial use where the license is noncommercial;
- missing required attribution/NOTICE;
- public push contains secrets/private keys/restricted data;
- exception lacks authority or scope;
- public code is described as OSI open source while governed solely by CC BY-NC-ND 4.0.

## Receipt fields

```text
schema
policy_id
policy_version
repo
branch
commit_or_tree
visibility_target
changed_paths_sha256
license_default
exceptions
unresolved_objects
blocking_codes
verdict
reviewed_by
model_or_agent
receipt_sha256
```

Do not claim that a push is license-verified unless this gate or an equivalent deterministic check actually ran and its receipt is preserved.

## FCO/FCG rule

License is a dependency edge, not decorative metadata. A claim/artifact cannot inherit broader reuse rights than its supporting atoms unless an independent legal basis is recorded.
