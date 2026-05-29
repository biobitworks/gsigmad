# How To Use gsigmad

`gsigmad` is a local governance layer for scientific and technical work. It
does not decide whether a claim is true. It makes hypothesis, prompt, EXP,
lab-notebook, audit, red-team, and adapter state explicit so an operator can
review the chain.

## Fast Path

```bash
mkdir my-governed-project
cd my-governed-project
gsigmad init .
gsigmad status

EXP_ID=$(gsigmad --json register \
  --type exploratory \
  --hypothesis "H0: the toy measurement distribution is unchanged." \
  --title "Toy measurement check" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["exp_id"])')

gsigmad run --dry-run "$EXP_ID"
gsigmad audit "$EXP_ID" --skip-citations
gsigmad redteam "$EXP_ID"
gsigmad status
```

Always use the returned `EXP_ID`. Do not hardcode an example experiment id;
numbering is part of the release surface and may change as templates evolve.

## With get-shit-done

Use this path when the repo also needs GSD planning, phases, and cross-agent
workflow scaffolding:

```bash
get-shit-done-cc --codex --claude --local --profile=core
gsd config-new-project
gsigmad init .
```

GSD owns project execution planning. `gsigmad` owns the experiment lifecycle,
scientific claim boundary, local lab notebook, and no-writeback science
governance defaults.

## Project Shapes Tested

The public adoption corpus covers six fresh synthetic repo shapes:

- generic Python science
- computational biology
- bioinformatics pipeline
- math/modeling notebook
- data-analysis-only
- non-science software repo

Each shape is tested in two paths: standalone `gsigmad` and
`get-shit-done + gsigmad`. The matrix exercises init, status, register,
dry-run, audit, redteam, prompt/EXP/lab-notebook artifacts, missing-adapter
behavior, no-writeback defaults, and returned EXP id reuse.

See [examples/projects/](../examples/projects/) for the versioned receipts and
per-case walkthroughs.

## Agent Runtime Notes

`gsigmad init` installs Agent Skills into both public agent paths:

- ChatGPT Codex / OpenAI Codex: `.agents/skills/gsigmad/SKILL.md`
- Claude Code: `.claude/skills/gsigmad/SKILL.md`

Local Ollama can be used by a consuming project as a model backend, but Ollama
does not promote claims or override gates. If Ollama is not running, start it
with:

```bash
ollama serve
```

Ollarma is optional. If it is not running, keep adapter status
`not_configured`; do not treat the bridge as passing. The local startup probe
used by the public matrix is:

```bash
ollarma serve
curl -sS http://127.0.0.1:8484/health | jq '.status, .startup_readiness.status'
```

## Expected Artifacts

After a healthy local adoption run, expect:

- `.gsigmad/config.yaml`
- `.gsigmad/LAB_NOTEBOOK.md`
- `.gsigmad/experiments/<returned EXP id>.yaml`
- `.agents/skills/gsigmad/SKILL.md`
- `.claude/skills/gsigmad/SKILL.md`
- optional adapter manifests marked `not_configured`

For combined GSD adoption, also expect:

- `.codex/get-shit-done/VERSION`
- `.claude/get-shit-done/VERSION`
- `.planning/config.json`

## Boundaries

Allowed public wording: `gsigmad provides deterministic governance guardrails
around AI-assisted scientific workflows`.

Deferred wording: ratified benchmark, DOI-backed release, live writeback,
Knowledge Graph promotion, or completed external review.

Prohibited wording: validates truth, proves biological mechanisms, replaces
domain review, autonomously discovers science, or turns web discussion into
scientific evidence.
