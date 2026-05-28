---
license: apache-2.0
pretty_name: gsigmad deterministic gate traces demo
language:
  - en
tags:
  - science-governance
  - reproducibility
  - agent-skills
  - synthetic
  - tabular
configs:
  - config_name: default
    data_files:
      - split: demo
        path: gate_traces.jsonl
---

# gsigmad Deterministic Gate Traces Demo

This dataset-card template is for a small public-safe demonstration of gsigmad
gate traces. Hugging Face renders dataset repository `README.md` files as
dataset cards and reads metadata from the YAML block at the top of the file.

The included `gate_traces.jsonl` rows are synthetic. They are designed to show
how release evidence can separate deterministic gate behavior from the creative
inference step that produced the claim under review.

## Contents

Each JSONL row records:

- `trial_id`: stable synthetic row identifier
- `domain`: example workflow domain
- `environment`: public or private release lane represented by the row
- `violation_category`: adversarial fixture category
- `expected_gate`: gate expected to adjudicate the row
- `gate_status`: `FAIL`, `MISSING_GATE`, or `RUNNER_LIMITATION`
- `caught`: whether the violation was caught in the represented measurement
- `deterministic_replicates`: repeated runs used for the row
- `unique_outputs`: number of unique gate outputs observed
- `creative_inference_boundary`: where probabilistic authoring ends and the
  deterministic gate begins

## Intended Use

Use this template to publish public release evidence after PI ratification and
sanitization. Keep fixture labels narrow: these rows do not support claims that
gsigmad catches all scientific misconduct or validates scientific truth.

## Not Included

This demo does not include raw research data, biological measurements, private
adapters, live database credentials, full internal trial artifacts, or unresolved
private planning state.
