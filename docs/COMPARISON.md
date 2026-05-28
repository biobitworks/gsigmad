# Comparison and Positioning

`gsigmad` is a governance overlay for AI-assisted science projects. It is not a
workflow engine, hosted ELN, public preregistration registry, model-training run
tracker, or scientific data platform.

Short form: `gsigmad` is not a workflow engine.

## Positioning Table

| System | Primary role | Keep using it for | How gsigmad differs |
| --- | --- | --- | --- |
| OSF | Public registrations, preregistrations, projects, and research records | Formal public preregistration, sharing project materials, DOI-backed OSF records when appropriate | `gsigmad` is local-first daily governance before or alongside any public OSF registration. |
| Galaxy | Web-based computational biomedical analysis platform with histories and workflows | Accessible bioinformatics execution, repeatable Galaxy workflows, shared analysis pages | `gsigmad` does not run Galaxy tools; it records preregistration, claims, and release gates around projects that may use Galaxy. |
| Renku | Collaborative data-science platform with code, data, workflows, provenance, and compute environments | Cloud/project environment management, dataset/code provenance, collaborative notebooks and sessions | `gsigmad` is lighter and repo-local; it focuses on AI-assistant governance boundaries rather than being the compute environment. |
| WorkflowHub | Registry for describing, sharing, and publishing computational workflows | Discovering and publishing workflow packages with workflow standards such as RO-Crate and CWL | `gsigmad` can govern an experiment that produces a workflow, but it is not a workflow registry. |
| Arvados | Big-data science platform for storage, compute, sharing, secure re-runs, and multi-cluster workflows | Large biomedical data management, secure compute, exact dataset reuse, scalable workflow execution | `gsigmad` does not manage clusters or large data storage; it records governance decisions and no-writeback boundaries. |
| MLflow | ML experiment/run tracking for parameters, metrics, artifacts, models, and run comparison | Training run tracking, model artifacts, metrics, model registry workflows | `gsigmad` tracks scientific governance state and claim promotion, not model training alone. |
| W&B | ML experiment tracking, dashboards, hyperparameters, metrics, and model artifacts | Collaborative ML run tracking, dashboards, artifacts, sweeps, and model monitoring | `gsigmad` can reference W&B evidence, but it does not replace the ML tracking dashboard. |
| VisTrails | Scientific workflow and provenance management with workflow history | Exploratory workflow provenance and scientific visualization workflows | `gsigmad` focuses on preregistration, claim classification, gate receipts, and AI-inference boundaries rather than visual workflow authoring. |

## Novelty Claim

The defensible novelty claim is narrow:

> `gsigmad` packages local-first scientific governance as a CLI plus Agent
> Skills bundle, and includes a deterministic boundary harness for showing
> where AI-assisted workflows remain rule-governed and where creative inference
> enters.

This is not a claim of priority over scientific workflow systems, public
registries, ELNs, or ML experiment trackers.

## Sources

- GitHub CITATION files: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files
- Zenodo GitHub integration: https://help.zenodo.org/docs/github/
- OSF registrations and preregistrations: https://help.osf.io/article/330-welcome-to-registrations
- Galaxy Project: https://galaxyproject.org/galaxy-project/
- Renku: https://renku-docs.readthedocs.io/en/latest/introduction/what-is-renku.html
- WorkflowHub: https://workflowhub.org/
- Arvados: https://doc.arvados.org/
- MLflow Tracking: https://mlflow.org/docs/latest/tracking
- Weights & Biases Experiments: https://docs.wandb.ai/models/track
- VisTrails: https://www.vistrails.org/
