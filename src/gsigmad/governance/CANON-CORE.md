# CANON-CORE

> **Status**: ACTIVE
> **Version**: 1.0.0
> **Schema**: governance/CANON-CORE-schema.json
> **Owner**: Getting Science Done
> **Applies to**: All projects that declare `extends: CANON-CORE v1.0.0`
> **Created**: 2026-03-31
> **Amendment protocol**: PI approval required; governed document; append-only change log
> **Signed**: SIG-20260331T000000Z-claude-sonnet-4-6-3325

---

## Purpose

CANON-CORE is the minimal set of universally non-negotiable invariants that apply to all scientific
work across the Getting Science Done ecosystem. It is NOT a mechanical intersection of existing project
CANON files — it is independently curated based on universal scientific integrity requirements.

Projects declare compliance with: `extends: CANON-CORE v1.0.0`

Alpha-Omega (creative writing) is explicitly excluded from science governance and does not extend CANON-CORE.

---

## Extension Interface

Project CANON files extend CANON-CORE by declaring in their header:

    extends: CANON-CORE v1.0.0

**Permitted without restriction:**
- Adding domain-specific invariants (biology vocabulary, toolchain rules, etc.)
- Adding domain-specific evidence types beyond MEASURED/INFERRED/HYPOTHESIS

**Overrides require explicit justification:**
- If a project cannot apply a CANON-CORE invariant, declare:

      override: invariant-N
      override-justification: "[why this invariant cannot apply to this domain]"

- Example: a demo mathematics project declares `override: invariant-1 (biology reference)` because the domain
  is mathematics-only; biology-inclusive language creates a domain incompatibility.
  All data still traces to source — mathematical derivations cited to proof or algorithm reference.

**Conflict rule:**
- Any project CANON that modifies a CANON-CORE invariant without a documented `override-justification`
  is in CANON conflict. `audit-claims` will flag CANON conflict violations.

---

## Invariants

### Invariant 1: No Fabricated Data, Claims, or Values

**Source:** Source Project A Invariant 1, Source Project B Invariant 1, Source Project C §7 Hypothesis Testing,
EXPERIMENT_STANDARDS.md §15

**Statement:** Every datum, computed value, and scientific claim must trace to a verifiable source:
a direct measurement, a peer-reviewed publication (with DOI/PMID), a validated model output, a
database entry, or an explicit HYPOTHESIS tag. Fabrication, imputation without documentation, and
parameter invention are prohibited. See EXPERIMENT_STANDARDS.md §15: parameters follow the same
evidence rules as claims — you cannot invent parameters any more than you can invent data. If no
publication justifies a parameter value, derive it from first principles and document the derivation,
or develop and validate a new methodology before use.

**Violation examples:**
- Hardcoding an effect size (e.g., `effect_size = 0.5`) without citing a source publication or
  prior measurement
- Using a default p-value threshold (e.g., alpha = 0.05) without documenting why that threshold
  is appropriate for the domain
- Imputing missing values with a mean without declaring the imputation as INFERRED and documenting
  the imputation method
- Writing any result file without tracing every computed value to its input data and algorithm

---

### Invariant 2: Run-ID-Specific Result Artifacts

**Source:** Source Project A Invariant 2, Source Project B Invariant 3, Source Project D §8

**Statement:** No experiment may write results to a fixed-name output file that can be silently
overwritten. Every result artifact is stamped with a unique run identifier (run-id, EXP-###, or
equivalent) that makes the output traceable to a single execution. The run identifier must appear
in the artifact filename or as a top-level metadata field in the artifact content.

**Violation examples:**
- Writing results to `output.csv` or `results.json` without a unique run-id suffix or subdirectory
- Re-using a prior EXP number for a new experiment (EXP-042 cannot be run twice)
- Generating a figure as `figure.png` that gets overwritten on each execution
- Storing intermediate pipeline outputs without a run-id provenance tag

---

### Invariant 3: Claim Classification Required

**Source:** Source Project A Invariant 6, Source Project C §7, Source Project D §8, Source Project B Invariant 6

**Statement:** Every scientific or operational claim must be tagged with exactly one of:
**MEASURED** (direct empirical observation), **INFERRED** (derived from measurements via model or
reasoning), or **HYPOTHESIS** (proposed but not yet tested). The tag must be accompanied by
documented justification. Unclassified claims cannot be promoted to shared governance artifacts
or knowledge graph entries.

**Violation examples:**
- Reporting a protein concentration without classifying it as MEASURED (direct assay) or INFERRED
  (computed from proxy signal)
- Stating "the model predicts X" without classifying X as INFERRED and citing the model version
  and inference method
- Listing a hypothesis in a pre-registration document without tagging it HYPOTHESIS
- Promoting an EXTREF artifact to the shared KG without verifying its claim classification tags

---

### Invariant 4: Append-Only Change Logs

**Source:** Source Project A Invariant 5, Source Project C §0 Signature Log

**Statement:** Corrections, updates, and retractions are made by appending a new signed entry,
never by editing or deleting prior entries. This applies to LAB_NOTEBOOK entries, CANON files,
EXP pre-registration records, and all governed documents. Edit history is preserved in git; the
document itself remains append-only. Retroactive modification of any governed record without
a corresponding append entry is a CANON violation.

**Violation examples:**
- Editing a previous LAB_NOTEBOOK entry to correct a typo (correct action: append a correction
  entry with the original text and corrected version)
- Deleting a failed experiment record from an EXP log
- Modifying CANON-CORE or a project CANON file without adding an entry to the Change Log
- Overwriting a SIG-ID signed entry to change its content after signing

---

### Invariant 5: Pre-Registration Before Execution for CONFIRMATORY Experiments

**Source:** Source Project A §9.2, Source Project C §7, Source Project D §8, EXPERIMENT_STANDARDS.md §2

**Statement:** CONFIRMATORY experiments must lock the null hypothesis (H₀), alternative
hypothesis (H₁), statistical test, rejection threshold (alpha), and Minimum Effect Size of
Interest (MESI) in a committed PROMPT-### document BEFORE the experiment script runs and BEFORE
data is loaded. The pre-registration commit timestamp must predate the data file's mtime.
Post-hoc hypothesis formulation (HARKing — Hypothesizing After Results are Known) violates
this invariant. EXPLORATORY experiments are exempt from pre-registration but must be classified
as EXPLORATORY before execution.

**Violation examples:**
- Running an analysis script, observing a significant result, then writing the hypothesis
  to match it (HARKing)
- Modifying H₀ or alpha after loading the data and before running the test
- Labeling an experiment CONFIRMATORY when the hypothesis was chosen based on preliminary
  data inspection
- Committing the pre-registration record with a timestamp later than the data file's mtime

---

### Invariant 6: Effect Size and Confidence Interval Mandatory

**Source:** Source Project A §9.3, EXPERIMENT_STANDARDS.md §4, Source Project C §7

**Statement:** p-values alone are insufficient evidence. Every statistical test must report
an effect size measure appropriate to the test type (Cohen's d for t-tests, η² for ANOVA,
Pearson r for correlation, Cramér's V for chi-square, hazard ratio for survival analysis,
or equivalent) accompanied by a 95% confidence interval. Claims citing only p < threshold
without effect size and CI are rejected by `audit-claims`. Effect sizes must be accompanied
by their own uncertainty quantification.

**Violation examples:**
- Reporting "p = 0.03, therefore significant" without Cohen's d and 95% CI
- Claiming a drug is effective based only on a log-rank test p-value without hazard ratio
  and confidence interval
- Including ANOVA results with p-values and F-statistics but no η² or partial η²
- Reporting a Spearman correlation coefficient without a 95% CI around the correlation estimate

---

### Invariant 7: Preserve Negative and Falsified Findings

**Source:** Source Project A Invariant 4, WORKFLOW_RULES §5, EXPERIMENT_STANDARDS.md §6

**Statement:** Null results, failed experiments, and disproven hypotheses are retained,
documented, and registered in the negative results log with the same rigor applied to positive
results. Selective reporting of positive results only constitutes a CANON violation. Negative
results must include a power analysis demonstrating the study was adequately powered to detect
the MESI (distinguishing a true null from an underpowered study). Falsified hypotheses must be
forward-linked from any future experiment that builds on the same research question.

**Violation examples:**
- Running 10 experiments, reporting the 2 that produced p < 0.05, and omitting the 8 null results
- Abandoning a negative experiment without a LAB_NOTEBOOK entry documenting the null finding
- Claiming "no significant effect found" without a power analysis showing the study could detect
  the MESI if it existed
- Proposing a new hypothesis in an EXP that builds on a prior hypothesis without linking to the
  falsified predecessor

---

### Invariant 8: Material Prompts Require Pre-Execution Red Team

**Source:** Source Project A Invariant 9, WORKFLOW_RULES §2b, CANON §8.7

**Statement:** Any prompt that can change scientific conclusions, modify benchmark design,
alter hypothesis classification, or mutate database/knowledge-graph state must document:
(a) the intended change and its scope, (b) a completed red team review identifying failure
modes and adversarial inputs, and (c) remediation constraints limiting execution scope.
This review must be present before execution, not appended after. For CONFIRMATORY
experiments, this gate is mandatory and blocking — execution cannot proceed without a
committed red team review entry.

**Violation examples:**
- Running a CONFIRMATORY experiment analysis prompt without a prior red team review
- Submitting a KG mutation prompt (add/update/delete edges or documents) without documenting
  failure modes and rollback strategy
- Appending a red team review entry after executing a prompt to retroactively satisfy the gate
- Claiming a prompt is not "material" to bypass the gate when it modifies evidence classification
  or hypothesis status

---

### Invariant 9: Agent Provenance and Signature Required

**Source:** Source Project A §5, Source Project C §0, Source Project D §0, Source Project B §4

**Statement:** Every modification to a governed document must carry the actual model identifier
in the SIG-ID format: `SIG-YYYYMMDDTHHMMSSZ-[agent]-[hash4]` where [agent] is the actual model
name (e.g., claude-sonnet-4-6, qwen2.5-coder-7b) and [hash4] is the first 4 characters of the
hex MD5 of the concatenated timestamp+agent+software_version string. Claiming a different model
identity in a SIG-ID is a provenance violation. Human modifications use `SIG-YYYYMMDDTHHMMSSZ-[human-initials]-[hash4]`.

**Hash4 generation:**
```python
import hashlib
sig_input = f"{timestamp}-{agent}-{software_version}"
hash4 = hashlib.md5(sig_input.encode()).hexdigest()[:4]
```

**Violation examples:**
- Signing a document as `claude-opus-4` when the actual executing model is `claude-sonnet-4-6`
- Omitting the SIG-ID from a LAB_NOTEBOOK entry or CANON file modification
- Using a fixed or invented hash4 value instead of computing it from timestamp+agent+version
- Batch-signing multiple entries with the same timestamp (each entry requires a unique timestamp)

---

## Change Log

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0.0 | 2026-03-31 | SIG-20260331T000000Z-claude-sonnet-4-6-3325 | Initial CANON-CORE authored from four source governance projects. 9 invariants curated (not mechanically intersected) covering data fabrication, run-id artifacts, claim classification, append-only logs, pre-registration (HARKing prevention), effect size + CI, negative findings preservation, red team gates, and agent provenance. |
