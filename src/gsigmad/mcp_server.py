"""MCP server exposing gsigmad commands as tools.

Requires: pip install gsigmad[mcp]
Run: gsigmad serve
Register: claude mcp add gsigmad -- gsigmad serve
"""
from __future__ import annotations

try:
    from fastmcp import FastMCP
except ImportError:
    raise SystemExit(
        "MCP support requires FastMCP. Install with: pip install gsigmad[mcp]"
    )

from pathlib import Path

mcp = FastMCP("gsigmad", instructions="Science governance CLI tools")


def _validate_project(project_path: str) -> Path:
    """Resolve project_path and validate .gsigmad/ exists.

    Returns the resolved path. Raises ValueError if not a gsigmad project.
    """
    target = Path(project_path).resolve()
    if not (target / ".gsigmad").is_dir():
        raise ValueError(
            f"Not a gsigmad project (no .gsigmad/ at {target}). "
            "Run gsigmad_init first."
        )
    return target


# ---------------------------------------------------------------------------
# MCP Tools -- each delegates to existing command logic
# ---------------------------------------------------------------------------


@mcp.tool
def gsigmad_init(project_path: str = ".") -> dict:
    """Initialize a gsigmad-governed science project at the given path."""
    from gsigmad.bundled_skills import install_bundled_skills
    from gsigmad.connectors import get_connector
    from gsigmad.governance.versioning import bootstrap_coordination_state
    from gsigmad.scaffold.templates import canon_template, default_config
    from gsigmad.scaffold.working_tree import scaffold_working_tree

    target = Path(project_path).resolve()
    gsigmad_dir = target / ".gsigmad"

    # Upgrade path
    if gsigmad_dir.exists():
        import yaml

        config_path = gsigmad_dir / "config.yaml"
        config = {}
        if config_path.is_file():
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        sv = config.get("schema_version", 1)

        from gsigmad.commands.init_cmd import CURRENT_SCHEMA_VERSION

        if sv >= CURRENT_SCHEMA_VERSION:
            return {
                "already_current": True,
                "schema_version": sv,
                "agent_hints": {
                    "next_tools": ["gsigmad_status", "gsigmad_register"],
                    "severity": None,
                },
            }

        scaffold_result = scaffold_working_tree(target)
        install_bundled_skills(target, overwrite=True)
        config["schema_version"] = CURRENT_SCHEMA_VERSION
        config_path.write_text(
            yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return {
            "upgraded": True,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "created": scaffold_result["created"],
            "skipped": scaffold_result["skipped"],
            "agent_hints": {
                "next_tools": ["gsigmad_status", "gsigmad_register"],
                "severity": None,
            },
        }

    # Fresh init
    connector = get_connector(target)
    config = default_config()
    config["project_name"] = target.name
    connector.initialize(target, config)
    bootstrap_coordination_state(target)

    canon_path = target / "CANON.md"
    if not canon_path.exists():
        canon_path.write_text(canon_template())

    install_bundled_skills(target)
    scaffold_result = scaffold_working_tree(target)

    return {
        "initialized": True,
        "path": str(target),
        "created": scaffold_result["created"],
        "skipped": scaffold_result["skipped"],
        "agent_hints": {
            "next_tools": ["gsigmad_register", "gsigmad_status"],
            "severity": None,
        },
    }


@mcp.tool
def gsigmad_ollarma_continuation(project_path: str = ".") -> dict:
    """Inspect the bounded local continuation payload for Ollarma."""
    from gsigmad.governance.ollarma_continuation import load_ollarma_continuation

    payload = load_ollarma_continuation(project_path)
    payload["agent_hints"] = {
        "next_tools": [],
        "severity": None if payload.get("suitable") else "advisory",
    }
    return payload


@mcp.tool
def gsigmad_register(
    exp_type: str = "exploratory",
    title: str = "",
    hypothesis: str = "",
    project_path: str = ".",
) -> dict:
    """Pre-register a new experiment with hypothesis and analysis plan template."""
    target = _validate_project(project_path)

    from gsigmad.connectors import get_connector
    from gsigmad.commands._experiment_creation import (
        anchor_opt_in_version,
        create_experiment_record,
    )

    connector = get_connector(target)
    if anchor_opt_in_version(connector) is not None:
        return {
            "error": (
                "Anchor-enabled projects must use the CLI register/scaffold flow with "
                "--anchors-file until MCP anchor parity lands."
            ),
            "agent_hints": {
                "next_tools": [],
                "severity": "error",
            },
        }

    classification = exp_type.upper()
    creation = create_experiment_record(
        target,
        connector,
        classification=classification,
        title=title,
        hypothesis=hypothesis,
        command_name="register",
    )

    return {
        "exp_id": creation["exp_id"],
        "path": str(creation["exp_path"]),
        "classification": classification,
        "agent_hints": {
            "next_tools": ["gsigmad_run"],
            "severity": None,
        },
    }


@mcp.tool
def gsigmad_run(exp_id: str, project_path: str = ".") -> dict:
    """Run governance gates for an experiment."""
    target = _validate_project(project_path)

    import importlib

    import yaml

    from gsigmad.commands.run import GATE_CHAIN, _call_gate
    from gsigmad.connectors import get_connector
    from gsigmad.governance.closure_chain import ensure_chain_for_experiment

    connector = get_connector(target)
    try:
        exp_record = connector.load_experiment(exp_id)
    except KeyError:
        return {
            "error": f"Experiment {exp_id} not found",
            "agent_hints": {"next_tools": ["gsigmad_register"], "severity": "error"},
        }

    classification = str(exp_record.get("classification", "")).upper()
    ensure_chain_for_experiment(target, exp_record)

    if classification not in GATE_CHAIN:
        return {
            "error": f"Unknown classification '{classification}'",
            "agent_hints": {"next_tools": [], "severity": "error"},
        }

    gates = GATE_CHAIN[classification]
    exp_path = str(target / ".gsigmad" / "experiments" / f"{exp_id}.yaml")
    results = []
    any_failed = False

    for gate_name, module_path, fn_name in gates:
        mod = importlib.import_module(module_path)
        gate_fn = getattr(mod, fn_name)
        gate_result = _call_gate(gate_name, gate_fn, fn_name, exp_record, exp_path)
        results.append(gate_result)
        if not gate_result["pass"]:
            any_failed = True

    return {
        "exp_id": exp_id,
        "classification": classification,
        "passed": not any_failed,
        "gates": results,
        "agent_hints": {
            "next_tools": ["gsigmad_audit"] if not any_failed else ["gsigmad_redteam"],
            "severity": "gate_failure" if any_failed else None,
        },
    }


@mcp.tool
def gsigmad_audit(exp_id: str = "", project_path: str = ".") -> dict:
    """Audit experiment governance compliance."""
    target = _validate_project(project_path)

    import importlib

    from gsigmad.connectors import get_connector
    from gsigmad.governance.closure_chain import list_chain_summaries

    connector = get_connector(target)

    if exp_id:
        try:
            exp_records = [connector.load_experiment(exp_id)]
        except KeyError:
            return {
                "error": f"Experiment {exp_id} not found",
                "agent_hints": {"next_tools": ["gsigmad_register"], "severity": "error"},
            }
    else:
        exp_records = connector.list_experiments()
        if not exp_records:
            return {
                "experiments": [],
                "passed": True,
                "note": "No experiments found",
                "agent_hints": {
                    "next_tools": ["gsigmad_register"],
                    "severity": None,
                },
            }

    mod = importlib.import_module("gsigmad.governance.gates.audit_claims")
    audit_gate = getattr(mod, "audit_claims_gate")

    all_results = []
    any_failed = False
    closure_by_exp = {item["exp_id"]: item for item in list_chain_summaries(target)}

    for exp_record in exp_records:
        current_exp_id = exp_record.get("exp_id", exp_id or "UNKNOWN")
        claims = exp_record.get("claims", [])

        if not claims:
            all_results.append({
                "exp_id": current_exp_id,
                "pass": True,
                "failures": [],
                "warnings": [],
                "note": "No claims to audit.",
            })
            continue

        gate_result = audit_gate(claims, verify_citations=False)
        result = {
            "exp_id": current_exp_id,
            "pass": gate_result["pass"],
            "failures": gate_result.get("failures", []),
            "warnings": gate_result.get("warnings", []),
            "closure": closure_by_exp.get(current_exp_id),
        }
        all_results.append(result)
        if not gate_result["pass"]:
            any_failed = True

    return {
        "experiments": all_results,
        "passed": not any_failed,
        "agent_hints": {
            "next_tools": ["gsigmad_export"] if not any_failed else ["gsigmad_classify"],
            "severity": "audit_failure" if any_failed else None,
        },
    }


@mcp.tool
def gsigmad_status(project_path: str = ".") -> dict:
    """Show project governance status."""
    target = _validate_project(project_path)

    from gsigmad.governance.closure_chain import list_chain_summaries
    from gsigmad.governance.compiler.session_status import get_exp_status_summary

    exp_result = get_exp_status_summary(str(target))

    drift_result = None
    drift_error = False
    if (target / ".gsigmad").is_dir():
        try:
            from gsigmad.governance.compiler.drift_check import check_drift

            drift_result = check_drift(str(target))
        except Exception:
            drift_error = True

    closure_result = list_chain_summaries(target)

    return {
        "experiments": exp_result,
        "drift": drift_result if not drift_error else {"error": "not yet tracked"},
        "closure": closure_result,
        "agent_hints": {
            "next_tools": ["gsigmad_register", "gsigmad_audit"],
            "severity": None,
        },
    }


@mcp.tool
def gsigmad_redteam(
    exp_id: str, challenge: str = "", project_path: str = "."
) -> dict:
    """Submit a red team challenge for an experiment."""
    target = _validate_project(project_path)

    from gsigmad.connectors import get_connector
    from gsigmad.governance.closure_chain import ensure_chain_for_experiment
    from gsigmad.governance.gates.red_team import check_red_team_gate

    connector = get_connector(target)
    try:
        exp_record = connector.load_experiment(exp_id)
    except KeyError:
        return {
            "error": f"Experiment {exp_id} not found",
            "agent_hints": {"next_tools": ["gsigmad_register"], "severity": "error"},
        }

    ensure_chain_for_experiment(target, exp_record)
    classification = str(exp_record.get("classification", "EXPLORATORY")).upper()
    prompt_fields = (
        exp_record.get("prompt_fields")
        or exp_record.get("red_team")
        or exp_record.get("hypothesis", {})
    )
    result = check_red_team_gate(classification, prompt_fields)

    return {
        "exp_id": exp_id,
        "classification": classification,
        "pass": result["pass"],
        "error": result.get("error"),
        "agent_hints": {
            "next_tools": ["gsigmad_run"] if result["pass"] else [],
            "severity": "redteam_failure" if not result["pass"] else None,
        },
    }


@mcp.tool
def gsigmad_export(exp_id: str, project_path: str = ".") -> dict:
    """Export an experiment bundle."""
    target = _validate_project(project_path)

    from gsigmad.governance.export.exporter import create_bundle

    bundle_path, manifest = create_bundle(exp_id=exp_id, gsd_root=str(target))

    return {
        "bundle_path": bundle_path,
        "manifest": manifest,
        "agent_hints": {
            "next_tools": [],
            "severity": None,
        },
    }


@mcp.tool
def gsigmad_drift(project_path: str = ".") -> dict:
    """Scan for governance drift."""
    target = _validate_project(project_path)

    from gsigmad.governance.compiler.drift_check import check_drift

    result = check_drift(str(target))

    return {
        **result,
        "agent_hints": {
            "next_tools": ["gsigmad_audit"] if result.get("pass") else [],
            "severity": "drift_warning" if not result.get("pass") else None,
        },
    }


@mcp.tool
def gsigmad_classify(
    claim_text: str = "", level: str = "", project_path: str = "."
) -> dict:
    """Classify an experiment claim as MEASURED, INFERRED, or HYPOTHESIS."""
    from gsigmad.commands.classify import _classify_text

    if not claim_text.strip():
        return {
            "error": "Provide claim_text to classify",
            "agent_hints": {"next_tools": [], "severity": "error"},
        }

    classification, rationale = _classify_text(claim_text)

    return {
        "classification": classification,
        "rationale": rationale,
        "agent_hints": {
            "next_tools": ["gsigmad_audit"],
            "severity": None,
        },
    }


@mcp.tool
def gsigmad_power(
    test_type: str = "",
    effect_size: float = 0.0,
    alpha: float = 0.05,
    power_target: float = 0.80,
    n_groups: int = 2,
    alternative: str = "two-sided",
    project_path: str = ".",
) -> dict:
    """Run power analysis for experiment design."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1

    result = compute_power_tier1(
        test_type=test_type,
        effect_size=effect_size,
        alpha=alpha,
        power_target=power_target,
        n_groups=n_groups,
        alternative=alternative,
    )

    return {
        **result,
        "agent_hints": {
            "next_tools": ["gsigmad_register"],
            "severity": "error" if result.get("pass") is False else None,
        },
    }


def main() -> None:
    """Entry point for running the MCP server directly."""
    mcp.run()


if __name__ == "__main__":
    main()
