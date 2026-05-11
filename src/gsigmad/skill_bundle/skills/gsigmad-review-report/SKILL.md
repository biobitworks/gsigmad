---
name: gsigmad-review-report
description: "Results-blind review of a locked registered report. Evaluates hypothesis clarity, analysis completeness, and decision tree validity WITHOUT accessing experiment results. Produces a structured ReviewFeedback JSON document."
disable-model-invocation: true
allowed-tools:
  - Read
  - Glob
  - Grep
---

# Review Report

Conduct a results-blind peer review of a locked registered report. You receive the pre-registration plan, decision tree, and hypothesis. You do NOT receive — and must NOT access — any experiment results.

## 1. Pre-Conditions

Before beginning review:

- The target EXP must have a locked registered report entry in `.agent/registered_reports.json`. Verify this by reading the file and confirming the EXP-### key is present. If it is absent, STOP and report: "EXP-### has no locked registered report. Lock the report using governance/reports/registered_report.py:lock_report() before requesting a review."
- The reviewer must have a valid SIG-ID in the format `SIG-YYYYMMDDTHHMMSSZ-[agent]-[hash4]`. This SIG-ID will populate the `reviewer_sig` and `blind_confirmed` self-declaration in the output.
- Review is model-agnostic: any agent with a valid SIG-ID may conduct the review. The review feedback carries the reviewer's identity and blind_confirmed self-declaration — the receiving team can assess the trust level accordingly.

## 2. CRITICAL: Files You May NOT Read

This section defines the blind enforcement boundary. Violating it produces a compromised review.

NEVER read any file under `results/` — this directory contains experiment outcome data.

NEVER read any section of `experiments/EXP_###_NAME.md` at or after the `## Results` heading. You may read sections before that heading (Objective, Methods, Hypothesis, Pre-Registration, Power Analysis).

NEVER read any file matching the patterns:
- `*_results_*.json`
- `*_output_*.json`
- `*_outcomes_*.json`
- `results/*.json`
- `results/*.csv`
- `results/*.tsv`

If you accidentally encounter result data (p-values, effect sizes, raw counts tied to outcomes):
- STOP immediately.
- Set `blind_confirmed` to `false` in the output ReviewFeedback JSON.
- Note the accidental exposure in the `recommendations` list.
- A review with `blind_confirmed: false` is a compromised review and should be discarded by the receiving team.

## 3. Step 1 — Load the Lock Record

Read `.agent/registered_reports.json`. Extract the entry for the target EXP-###.

From the lock record, note:
- `pre_reg_file`: path to the pre-registration file (this is the primary review artifact)
- `commit_sha`: the git commit SHA at the time of locking (for audit trail reference — do not use for review scoring)
- `locked_at`: ISO 8601 timestamp when the plan was locked
- `locked_by`: SIG-ID of the agent who locked the report

If the target EXP-### key is absent from `registered_reports.json`, STOP. See Pre-Conditions above.

## 4. Step 2 — Read Permitted Files Only

Read only the following files. Do not read any other files.

**Required reads:**

1. The pre-registration file at the `pre_reg_file` path from the lock record. Read the full file content. If the file contains a `## Results` section, read only the content before that heading — stop reading at the `## Results` line.

2. If a `prompts/PROMPT_###_*.md` file exists for this EXP-### (use Glob: `prompts/PROMPT_*_*.md` filtered to match the experiment number), read it for additional hypothesis context. Apply the same rule: stop reading at any `## Results` or results-adjacent heading.

3. Read `governance/CANON-CORE-compact.md` for the review standards this project operates under, specifically: evidence classification rules (MEASURED/INFERRED/HYPOTHESIS), CONFIRMATORY experiment requirements (H0, H1, alpha, MESI), and decision tree validity criteria.

**Do not read:**
- `results/` directory (any contents)
- `experiments/EXP_###_NAME.md` sections after `## Results`
- Any `*_results_*.json`, `*_output_*.json`, or `*_outcomes_*.json` file
- `governance/compiler/metaprompt.py` or other implementation files not needed for review criteria

## 5. Step 3 — Evaluate Hypothesis Clarity (score 1–5)

Score the clarity and operationalizability of the hypothesis stated in the pre-registration plan.

| Score | Criteria |
|-------|----------|
| 5 | H0 and H1 are stated, mutually exclusive, and contain an operationalized effect size (MESI). H0 is a precise null (e.g., "no difference greater than d=0.3"). H1 is the directional alternative. The minimum effect size of interest (MESI) is a numeric value with units. |
| 4 | H0 and H1 are clearly stated and mutually exclusive. MESI is present but vaguely operationalized (e.g., "a meaningful increase" without a numeric threshold). |
| 3 | H0 and H1 are stated but one of the following is missing or vague: MESI is absent, the effect direction is unstated, or the hypotheses are not clearly mutually exclusive. |
| 2 | H0 or H1 is present but the other is absent or implied. The reader must infer the null condition. MESI is absent. |
| 1 | H0 or H1 is absent, circular (e.g., "we expect to find differences"), or untestable given the described data collection. |

Apply this rubric strictly. If the pre-registration uses non-standard notation, map it to H0/H1 before scoring.

## 6. Step 4 — Evaluate Analysis Plan Completeness (score 1–5)

Score the completeness of the stated analysis plan.

| Score | Criteria |
|-------|----------|
| 5 | All five elements present and fully specified: (1) statistical test by name (e.g., "two-sided independent samples t-test"), (2) alpha level as a numeric value (e.g., α=0.05), (3) sample size N with rationale, (4) power analysis tier (Tier 1 exact, Tier 2 approximate, or Tier 3 expert justification), and (5) multiple-comparisons correction method if more than one test is planned. |
| 4 | All five elements present. One element is underspecified but present (e.g., N is stated as a range, or the correction method is named but the corrected threshold is not calculated). |
| 3 | Four of five elements present. One element is missing entirely (most commonly: power analysis tier or correction method for multiple tests). |
| 2 | Three of five elements present. The statistical test is named but alpha or N is absent. |
| 1 | Statistical test is unnamed (e.g., "we will use appropriate statistics"), or both alpha and N are absent. |

## 7. Step 5 — Evaluate Decision Tree Validity (score 1–5)

Score the validity and completeness of the decision tree for interpreting results.

| Score | Criteria |
|-------|----------|
| 5 | Decision tree covers all three outcome branches: (a) reject H0, (b) fail to reject H0, (c) indeterminate/inconclusive. Each branch leads to a defined action (e.g., "proceed to confirmatory replication", "register as negative result in NEGATIVE_RESULTS_REGISTRY.md", "collect additional data up to N_max"). No circular references. Edge cases (data quality failures, missing data above threshold, technical failures) are handled with defined fallback branches. |
| 4 | All three main outcome branches covered with defined actions. One edge case (data quality or technical failure) is unhandled or delegated to "PI discretion." |
| 3 | Main branches (reject / fail-to-reject) covered with defined actions. Indeterminate branch is absent or handled as "fail-to-reject." Edge cases are unhandled. |
| 2 | Only the "reject H0" branch is described in detail. Fail-to-reject and indeterminate branches lead to vague outcomes (e.g., "revisit analysis"). |
| 1 | Decision tree is absent, or all branches lead to the same outcome regardless of result (e.g., "if the experiment works, proceed; otherwise, troubleshoot"). |

## 8. Step 6 — Write Recommendations

Write specific, actionable recommendations based on your scores. Rules:

- A score of 4 or 5 on any dimension requires no mandatory recommendation for that dimension (though you may note a minor improvement).
- A score of 3 or below on any dimension requires at least one recommendation that: (a) identifies the specific section or field that is weak, (b) states what is missing or unclear, and (c) provides a concrete suggestion for improvement. Do NOT reference result values in recommendations.
- Recommendations must reference the pre-registration file, not the results.
- Minimum recommendations: 0. Maximum recommendations: no limit.
- Example well-formed recommendation: "analysis_completeness: The power analysis tier is absent. Add a `power_analysis:` block to the pre-registration specifying: required_n, effect_size_mesi, alpha, achieved_power, and tier (1/2/3) per governance/gates/power_analysis.py requirements."
- Example malformed recommendation (do NOT write): "The p-value was borderline — the alpha level should have been set lower." (This references a result.)

## 9. Step 7 — Output ReviewFeedback JSON

Write the structured feedback to `experiments/reviews/EXP_###_review_{N}.json` where:
- `EXP_###` is the experiment identifier (e.g., `EXP_001`)
- `{N}` is the next available review number, computed as: `len(glob("experiments/reviews/EXP_###_review_*.json")) + 1`

Create the `experiments/reviews/` directory if it does not exist (use Bash: `mkdir -p experiments/reviews`).

The JSON content must match the ReviewFeedback schema exactly:

```json
{
  "exp_id": "EXP-###",
  "reviewed_at": "<ISO 8601 UTC timestamp, e.g. 2026-04-01T12:00:00Z>",
  "reviewer_sig": "<SIG-ID of reviewing agent, e.g. SIG-20260401T120000Z-reviewer-a1b2>",
  "hypothesis_clarity": <integer 1-5>,
  "analysis_completeness": <integer 1-5>,
  "decision_tree_validity": <integer 1-5>,
  "recommendations": [
    "recommendation 1 text",
    "recommendation 2 text"
  ],
  "blind_confirmed": true
}
```

Set `blind_confirmed` to `false` if any results data was accessed during this review session (even accidentally). A review with `blind_confirmed: false` is compromised and should be discarded by the receiving team.

All score fields (`hypothesis_clarity`, `analysis_completeness`, `decision_tree_validity`) must be integers in the range [1, 5]. Any score below 4 must have a corresponding entry in `recommendations` citing the specific weakness.

## 10. Post-Conditions

After writing the ReviewFeedback JSON, verify:

- `experiments/reviews/EXP_###_review_{N}.json` exists on disk.
- The file is valid JSON (no trailing commas, no comments).
- All three score fields are integers in the range [1, 5].
- `blind_confirmed` accurately reflects whether results were accessed during this review session.
- If `blind_confirmed` is `false`, ensure the `recommendations` list includes an entry noting the accidental exposure.

Report back:
- Review file path
- Scores: hypothesis_clarity={X}, analysis_completeness={X}, decision_tree_validity={X}
- Recommendation count
- blind_confirmed status

## Anti-Patterns

**Do NOT use `assemble_metaprompt()`** for this skill. The blind constraint is enforced by this SOP's explicit permitted-files list in Step 2. Calling the metaprompt compiler would assemble context from the full block registry, which may include result artifacts.

**Do NOT write review feedback to the pre-registration file or lab notebook.** The ReviewFeedback JSON lives in `experiments/reviews/` — it is a separate artifact from the pre-registration and from the lab notebook. Writing review scores to the pre-registration file would corrupt the locked artifact.

**Do NOT produce a score below 4 without a corresponding recommendation** citing the specific weakness. A low score without a recommendation is not actionable for the author and violates the purpose of peer review.

**Do NOT use a glob or wildcard that touches `results/`** when looking for the pre-registration file. Always use the `pre_reg_file` path from the lock record in `.agent/registered_reports.json`.

**Do NOT run the experiment or call any gate functions (power_analysis, temporal_integrity, red_team, data_contract)** during review. The review evaluates the plan quality, not whether the plan passes the governance gates. Gate results, if present, are available in the pre-registration file's `gates:` block — you may read that block, but you may not re-run the gates.
