"""Recovery diagnostics and repair helpers for governed local state."""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from gsigmad.governance.closure_chain import STAGE_ORDER, load_chain_state, save_chain_state
from gsigmad.governance.kg.queue_ops import inspect_queue_state, quarantine_queue_line, read_retry_state
from gsigmad.hub.ledger import best_effort_append_command_w5, build_w5_record, verify_ledger_chain

QUEUE_FILES = (
    "kg_queue.jsonl",
    "kg_queue_failed.jsonl",
    "kg_queue_expired.jsonl",
    "kg_queue_quarantine.jsonl",
)
TERMINAL_STATES = {"COMPLETED", "ABANDONED", "BLOCKED", "FAILED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _actor_identity() -> str:
    return (
        os.environ.get("GSD_ACTOR")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or getpass.getuser()
        or "unknown"
    )


def _issue(
    *,
    severity: str,
    category: str,
    code: str,
    description: str,
    exp_id: str | None,
    auto_repairable: bool,
    suggested_action: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "code": code,
        "description": description,
        "exp_id": exp_id,
        "auto_repairable": auto_repairable,
        "suggested_action": suggested_action,
    }


def _load_experiments(project_root: Path) -> dict[str, dict[str, Any]]:
    experiments: dict[str, dict[str, Any]] = {}
    experiments_dir = project_root / ".gsigmad" / "experiments"
    if not experiments_dir.is_dir():
        return experiments
    for path in sorted(experiments_dir.glob("EXP-*.yaml")):
        record = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(record, dict):
            exp_id = record.get("exp_id") or path.stem
            experiments[str(exp_id)] = record
    return experiments


def _resolved_codes(chain: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for event in chain.get("recovery_events", []):
        for code in event.get("resolves", []):
            codes.add(str(code))
    return codes


def _has_backward_transition(chain: dict[str, Any]) -> bool:
    previous: int | None = None
    for event in chain.get("history", []):
        stage = event.get("stage")
        if stage not in STAGE_ORDER:
            continue
        current = STAGE_ORDER[stage]
        if previous is not None and current < previous:
            return True
        previous = current
    return False


def _is_stuck_closure(chain: dict[str, Any]) -> bool:
    if chain.get("terminal_state") in TERMINAL_STATES:
        return False
    current_stage = chain.get("current_stage")
    if current_stage not in {"RESULTS", "RT", "REM"}:
        return False
    if current_stage == "RESULTS":
        return not (chain.get("rt_id") or chain.get("rem_id") or chain.get("lab_notebook_entry"))
    if current_stage in {"RT", "REM"}:
        return chain.get("lab_notebook_entry") is None
    return False


def _diagnose_ledger(project_root: Path) -> list[dict[str, Any]]:
    try:
        verdict = verify_ledger_chain(project_root)
    except Exception as exc:
        return [
            _issue(
                severity="error",
                category="ledger",
                code="LEDGER_READ_ERROR",
                description=f"Ledger could not be read or parsed: {exc}",
                exp_id=None,
                auto_repairable=True,
                suggested_action="gsigmad recover repair --target ledger --apply --attestation '<reason>'",
            )
        ]

    if verdict.get("pass"):
        return []
    return [
        _issue(
            severity="error",
            category="ledger",
            code="BROKEN_LEDGER_CHAIN",
            description=(
                f"Ledger verification failed with {verdict.get('error')} "
                f"at entry {verdict.get('entry_index')}"
            ),
            exp_id=None,
            auto_repairable=True,
            suggested_action="gsigmad recover repair --target ledger --apply --attestation '<reason>'",
        )
    ]


def _diagnose_queue(project_root: Path) -> list[dict[str, Any]]:
    snapshot = inspect_queue_state(project_root)
    if snapshot["counts"]["quarantine"] <= 0:
        return []
    return [
        _issue(
            severity="error",
            category="queue",
            code="QUEUE_CORRUPTION",
            description=f"Queue inspection found {snapshot['counts']['quarantine']} quarantined malformed entries",
            exp_id=None,
            auto_repairable=True,
            suggested_action="gsigmad recover repair --target queue --apply --attestation '<reason>'",
        )
    ]


def diagnose_recovery_state(project_root: Path | str) -> dict[str, Any]:
    """Return a read-only diagnosis of local governance state corruption."""
    root = Path(project_root).resolve()
    experiments = _load_experiments(root)
    state = load_chain_state(root, create=False)
    issues: list[dict[str, Any]] = []

    for exp_id in sorted(experiments):
        if exp_id not in state.get("chains", {}):
            issues.append(
                _issue(
                    severity="error",
                    category="closure",
                    code="MISSING_CHAIN",
                    description=f"{exp_id} exists on disk but has no closure-chain entry",
                    exp_id=exp_id,
                    auto_repairable=True,
                    suggested_action="gsigmad recover repair --target closure --apply --attestation '<reason>'",
                )
            )

    for chain_id, chain in sorted(state.get("chains", {}).items()):
        resolved = _resolved_codes(chain)
        if chain_id not in experiments and "ORPHANED_CHAIN" not in resolved:
            issues.append(
                _issue(
                    severity="error",
                    category="closure",
                    code="ORPHANED_CHAIN",
                    description=f"{chain_id} is tracked in closure state but has no EXP record on disk",
                    exp_id=chain_id,
                    auto_repairable=False,
                    suggested_action="Review or recreate the missing EXP record before automated repair",
                )
            )

        chain_exp_id = chain.get("exp_id")
        if chain_exp_id and chain_exp_id != chain_id and "DANGLING_REFERENCE" not in resolved:
            issues.append(
                _issue(
                    severity="error",
                    category="closure",
                    code="DANGLING_REFERENCE",
                    description=f"Closure entry key {chain_id} points at mismatched exp_id {chain_exp_id}",
                    exp_id=chain_id,
                    auto_repairable=False,
                    suggested_action="Inspect closure state and EXP files before manual correction",
                )
            )

        if _has_backward_transition(chain) and "BACKWARD_TRANSITION" not in resolved:
            issues.append(
                _issue(
                    severity="error",
                    category="closure",
                    code="BACKWARD_TRANSITION",
                    description=f"{chain_id} contains a backward stage transition in closure history",
                    exp_id=chain_id,
                    auto_repairable=True,
                    suggested_action="gsigmad recover repair --target closure --apply --attestation '<reason>'",
                )
            )

        if _is_stuck_closure(chain) and "STUCK_CLOSURE" not in resolved:
            issues.append(
                _issue(
                    severity="error",
                    category="closure",
                    code="STUCK_CLOSURE",
                    description=f"{chain_id} is stuck at {chain.get('current_stage')} without terminal closeout",
                    exp_id=chain_id,
                    auto_repairable=True,
                    suggested_action="gsigmad recover repair --target closure --apply --attestation '<reason>'",
                )
            )

    issues.extend(_diagnose_ledger(root))
    issues.extend(_diagnose_queue(root))

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    auto_repairable = sum(1 for issue in issues if issue["auto_repairable"])
    return {
        "diagnosed_at": _utc_now(),
        "project_root": str(root),
        "issues": issues,
        "summary": {
            "healthy": not issues,
            "issue_count": len(issues),
            "errors": errors,
            "warnings": warnings,
            "auto_repairable": auto_repairable,
        },
    }


def review_recovery_state(project_root: Path | str) -> dict[str, Any]:
    """Return a read-only operator review surface for terminal queue work."""
    root = Path(project_root).resolve()
    snapshot = inspect_queue_state(root)
    dead_letter = list(snapshot["entries"]["failed"]) + list(snapshot["entries"]["expired"])
    non_retryable = [
        entry
        for entry in dead_letter
        if (entry.get("failure_class") or "").lower() == "permanent"
    ]
    retry_state = read_retry_state(root)
    return {
        "reviewed_at": _utc_now(),
        "project_root": str(root),
        "summary": {
            "dead_letter": len(dead_letter),
            "non_retryable": len(non_retryable),
            "retry_evidence": len(retry_state),
        },
        "entries": {
            "dead_letter": dead_letter,
            "non_retryable": non_retryable,
            "retry_state": retry_state,
        },
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _backup_path(path: Path, *, suffix: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.{suffix}-{stamp}")


def _backup_file(path: Path, *, suffix: str = "backup") -> dict[str, Any]:
    backup = _backup_path(path, suffix=suffix)
    payload = path.read_bytes() if path.exists() else b""
    backup.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, backup)
    else:
        backup.write_bytes(payload)
    return {
        "source_path": str(path),
        "backup_path": str(backup),
        "sha256": _sha256_bytes(payload),
    }


def _iter_jsonl_lines(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    if not path.exists():
        return valid, invalid
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError("JSONL entry is not an object")
            valid.append(payload)
        except Exception as exc:
            invalid.append({"raw_line": raw_line, "error": str(exc)})
    return valid, invalid


def _seed_recovery_ledger(project_root: Path, attestation: str, backup: dict[str, Any]) -> dict[str, Any]:
    ledger_file = project_root / ".gsigmad" / "ledger" / "governance.jsonl"
    record = build_w5_record(
        who={"actor": _actor_identity(), "runtime": "gsigmad-cli"},
        what={"command": "recover", "mode": "cli"},
        where={"project_root": str(project_root), "exp_id": None},
        why={"action": "ledger_recovery"},
        prev_hash=None,
        metadata={
            "marker": "CHAIN_BREAK",
            "attestation": attestation,
            "backup_path": backup["backup_path"],
            "backup_sha256": backup["sha256"],
        },
    )
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _repair_ledger(project_root: Path, attestation: str) -> dict[str, Any]:
    ledger_file = project_root / ".gsigmad" / "ledger" / "governance.jsonl"
    backup = _backup_file(ledger_file, suffix="corrupt")
    entry = _seed_recovery_ledger(project_root, attestation, backup)
    return {"backup": backup, "entry": entry}


def _append_repair_audit(
    project_root: Path,
    *,
    action: str,
    attestation: str,
    backups: list[dict[str, Any]],
    target: str,
) -> dict[str, Any] | None:
    return best_effort_append_command_w5(
        project_root,
        command="recover",
        action=action,
        metadata={
            "attestation": attestation,
            "target": target,
            "marker": "CHAIN_BREAK" if target == "closure" else None,
            "backups": backups,
        },
    )


def _repair_queue(project_root: Path, attestation: str) -> dict[str, Any]:
    agent_root = project_root / ".agent"
    quarantine_path = agent_root / "kg_queue_quarantine.jsonl"
    backups: list[dict[str, Any]] = []
    repaired_files: list[dict[str, Any]] = []

    for name in QUEUE_FILES:
        source = agent_root / name
        valid, invalid = _iter_jsonl_lines(source)
        if not invalid:
            continue
        backup = _backup_file(source, suffix="corrupt")
        backups.append(backup)
        source.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(json.dumps(entry, ensure_ascii=False) for entry in valid)
        source.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        for item in invalid:
            quarantine_queue_line(
                quarantine_path,
                source_path=source,
                raw_line=item["raw_line"],
                error=item["error"],
            )
        repaired_files.append(
            {
                "source_path": str(source),
                "valid_entries": len(valid),
                "quarantined_entries": len(invalid),
            }
        )

    entry = None
    if repaired_files:
        entry = _append_repair_audit(
            project_root,
            action="repair_queue",
            attestation=attestation,
            backups=backups,
            target="queue",
        )
    return {"backups": backups, "repaired_files": repaired_files, "entry": entry}


def _new_chain(exp_id: str, exp_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "exp_id": exp_id,
        "task_id": exp_record.get("task_id"),
        "prompt_id": exp_record.get("prompt_id"),
        "results_id": None,
        "rt_id": None,
        "rem_id": None,
        "lab_notebook_entry": None,
        "current_stage": "EXP",
        "terminal_state": None,
        "history": [],
        "recovery_events": [],
    }


def _repair_closure(project_root: Path, diagnosis: dict[str, Any], attestation: str) -> dict[str, Any]:
    closure_path = project_root / ".gsigmad" / "closure_chain.json"
    state = load_chain_state(project_root, create=False)
    experiments = _load_experiments(project_root)
    backups: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    modified = False

    for issue in diagnosis["issues"]:
        if issue["category"] != "closure" or not issue["auto_repairable"]:
            continue
        exp_id = issue.get("exp_id")
        if not exp_id:
            continue
        if issue["code"] == "MISSING_CHAIN" and exp_id in experiments and exp_id not in state["chains"]:
            chain = _new_chain(exp_id, experiments[exp_id])
            chain.setdefault("recovery_events", []).append(
                {
                    "timestamp": _utc_now(),
                    "marker": "CHAIN_BREAK",
                    "attestation": attestation,
                    "resolves": ["MISSING_CHAIN"],
                    "description": "Reconstructed missing closure-chain entry from EXP record",
                }
            )
            state["chains"][exp_id] = chain
            actions.append({"code": "MISSING_CHAIN", "exp_id": exp_id})
            modified = True
            continue

        if issue["code"] in {"STUCK_CLOSURE", "BACKWARD_TRANSITION"} and exp_id in state["chains"]:
            chain = state["chains"][exp_id]
            events = chain.setdefault("recovery_events", [])
            events.append(
                {
                    "timestamp": _utc_now(),
                    "marker": "CHAIN_BREAK",
                    "attestation": attestation,
                    "resolves": [issue["code"]],
                    "description": issue["description"],
                }
            )
            actions.append({"code": issue["code"], "exp_id": exp_id})
            modified = True

    entry = None
    if modified:
        backups.append(_backup_file(closure_path, suffix="repair"))
        save_chain_state(project_root, state)
        entry = _append_repair_audit(
            project_root,
            action="repair_closure",
            attestation=attestation,
            backups=backups,
            target="closure",
        )
    return {"backups": backups, "actions": actions, "entry": entry}


def repair_recovery_state(
    project_root: Path | str,
    *,
    target: str = "all",
    apply: bool = False,
    attestation: str | None = None,
) -> dict[str, Any]:
    """Preview or apply governed recovery for supported local-state targets."""
    root = Path(project_root).resolve()
    diagnosis = diagnose_recovery_state(root)
    targets = ["ledger", "queue", "closure"] if target == "all" else [target]
    if apply and not attestation:
        raise ValueError("Apply-mode recovery requires --attestation")

    actions: list[dict[str, Any]] = []
    backups: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    for current in targets:
        if current == "ledger":
            relevant = [issue for issue in diagnosis["issues"] if issue["code"] in {"BROKEN_LEDGER_CHAIN", "LEDGER_READ_ERROR"}]
            if not relevant:
                continue
            actions.append({"target": "ledger", "issues": relevant})
            if apply:
                ledger_result = _repair_ledger(root, attestation or "")
                backups.append(ledger_result["backup"])
                audit.append({"target": "ledger", "entry": ledger_result["entry"]})
        elif current == "queue":
            relevant = [issue for issue in diagnosis["issues"] if issue["code"] == "QUEUE_CORRUPTION"]
            if not relevant:
                continue
            actions.append({"target": "queue", "issues": relevant})
            if apply:
                queue_result = _repair_queue(root, attestation or "")
                backups.extend(queue_result["backups"])
                if queue_result["entry"] is not None:
                    audit.append({"target": "queue", "entry": queue_result["entry"]})
        elif current == "closure":
            relevant = [
                issue
                for issue in diagnosis["issues"]
                if issue["category"] == "closure" and issue["auto_repairable"]
            ]
            if not relevant:
                continue
            actions.append({"target": "closure", "issues": relevant})
            if apply:
                closure_result = _repair_closure(root, diagnosis, attestation or "")
                backups.extend(closure_result["backups"])
                if closure_result["entry"] is not None:
                    audit.append({"target": "closure", "entry": closure_result["entry"]})
        else:
            raise ValueError(f"Unsupported recovery target: {current}")

    return {
        "project_root": str(root),
        "target": target,
        "targets": targets,
        "dry_run": not apply,
        "applied": apply,
        "attestation": attestation,
        "diagnosis": diagnosis["summary"],
        "actions": actions,
        "backups": backups,
        "audit": audit,
    }
