# Portfolio License Policy

Policy ID: `BIOBITWORKS-LICENSE-POLICY-v1`
Status: `DRAFT_FOR_ROLLOUT`
Default license: `CC-BY-NC-ND-4.0`

## Default

All newly authored BiobitWorks/Cellico project material defaults to:

**Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)**

This includes, unless an explicit exception is recorded:

- papers and preprints
- article prose
- documentation
- figures and tables
- notebooks
- experiment records
- prompts and agent handoffs
- schemas and manifests
- source code and scripts
- model cards and release notes
- datasets and derived research objects where BiobitWorks has authority to license them

Canonical license identifier: `CC-BY-NC-ND-4.0`.
Canonical license URL: `https://creativecommons.org/licenses/by-nc-nd/4.0/`.

## Meaning of the default

The default permits redistribution with attribution for noncommercial purposes. Adapted material may be made for noncommercial purposes but may not be shared under the license. Commercial use is not licensed.

This policy intentionally chooses a restrictive public-use surface. Code governed solely by CC BY-NC-ND 4.0 must not be represented as OSI-approved open-source software.

## Authority boundary

This policy applies only where BiobitWorks/Cellico or the relevant rights holder has authority to grant the license.

It MUST NOT silently relicense:

- third-party source code
- upstream repositories
- externally licensed datasets
- papers or figures owned by others
- contributor-owned material where relicensing rights were not granted
- public-domain material

For those objects, preserve the original license and provenance at atom/FCO level.

## Upstream and mixed-license objects

Every imported atom/FCO must record:

- source URI or repository
- exact version / commit / DOI when available
- source SHA-256 when computed
- upstream license identifier
- attribution requirements
- modification / redistribution constraints
- human/model/agent derivation provenance
- whether the object may be redistributed, transformed, or only cited

If license status is unknown, set:

`LICENSE_STATUS=UNRESOLVED`

and fail closed for public redistribution.

## Push gate

Every private or public push that contains substantive project work SHOULD run a deterministic license gate. Public release/promotion MUST run it.

Required checks:

1. repo-level license policy is declared;
2. newly created owned artifacts default to `CC-BY-NC-ND-4.0` unless an exception record exists;
3. imported/third-party atoms retain their upstream license rather than inheriting the repo default;
4. every source atom used in a claim has a license state;
5. `LICENSE_STATUS=UNRESOLVED` blocks redistribution/public promotion of that atom;
6. files carrying incompatible or more restrictive upstream terms are not rewritten as CC BY-NC-ND;
7. attribution and NOTICE requirements are retained;
8. generated/AI-assisted material records model/agent provenance separately from copyright/license status;
9. secrets/private keys/restricted data are not included;
10. the push receipt records branch, commit, gate verdict, policy version, and exceptions.

Verdicts:

- `PASS`: license policy and all included source licenses resolved.
- `PASS_WITH_EXCEPTIONS`: explicit, documented exceptions exist and are compatible with the destination.
- `BLOCK`: unresolved, conflicting, unauthorized, or missing license state.

## Private repositories

Private visibility does not waive provenance/license tracking. The same source-license registry should be maintained so later public promotion can be evaluated mechanically.

A private push may use `PASS_WITH_EXCEPTIONS` for material that is legally usable internally but not redistributable. Such objects must be marked `PUBLIC_PROMOTION_BLOCKED=true`.

## Public repositories and releases

Public promotion requires:

- all public objects licensed or otherwise lawfully redistributable;
- exact attribution preserved;
- no unresolved third-party license state;
- no private/restricted source leakage;
- public-release manifest and license-gate receipt.

## Software warning

Creative Commons recommends software-specific licenses rather than CC licenses for software. This portfolio policy nevertheless uses CC BY-NC-ND 4.0 as the default because the rights holder has chosen noncommercial/no-derivatives restrictions as the base policy. Repositories intended to be interoperable with conventional open-source software ecosystems require an explicit exception and must record the alternative license at repository/file level.

## Exceptions

An exception must state:

- object/repository/path
- alternative license
- reason
- authority to apply it
- scope
- date
- approver

Do not infer exceptions from historical repository state.

## FCO/FCG integration

License state is a first-class custody dependency.

Minimum FCO license fields:

```text
license.id
license.source
license.status
license.attribution
license.derivatives_allowed
license.commercial_use_allowed
license.redistribution_allowed
license.exception_id
```

A downstream Seed of Truth or claim cannot have a broader redistribution/license state than the atoms supporting it unless an independent legal basis is recorded.

## Claim ceiling

This policy is an operational licensing/governance rule. It is not legal advice and does not itself establish ownership, copyrightability, patent rights, fair use, or permission from third parties.
