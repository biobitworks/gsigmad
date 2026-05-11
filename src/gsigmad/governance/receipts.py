"""Append-only helpers for canonical stage receipts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from gsigmad.governance.execution_contract import StageReceipt

RECEIPTS_DIR = Path(".gsigmad") / "receipts"


def receipts_root(project_root: Path | str) -> Path:
    return Path(project_root).resolve() / RECEIPTS_DIR


def run_receipts_dir(project_root: Path | str, run_id: str) -> Path:
    return receipts_root(project_root) / run_id


def write_stage_receipt(project_root: Path | str, receipt: StageReceipt | dict[str, Any]) -> dict[str, str]:
    """Write one receipt append-only under `.gsigmad/receipts/<run_id>/`."""
    root = Path(project_root).resolve()
    model = receipt if isinstance(receipt, StageReceipt) else StageReceipt.model_validate(receipt)
    target_dir = run_receipts_dir(root, model.run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    next_index = len(sorted(target_dir.glob("*.yaml"))) + 1
    receipt_id = model.receipt_id or f"RECEIPT-{model.run_id}-{next_index:03d}"
    payload = model.model_copy(update={"receipt_id": receipt_id}).model_dump(mode="json")
    filename = f"{next_index:03d}-{model.stage.value.replace('/', '-')}.yaml"
    receipt_path = target_dir / filename
    with receipt_path.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)

    return {
        "receipt_id": receipt_id,
        "receipt_relpath": receipt_path.relative_to(root).as_posix(),
    }


def load_stage_receipt(project_root: Path | str, receipt_path: Path | str) -> StageReceipt:
    """Load one canonical stage receipt from disk."""
    root = Path(project_root).resolve()
    path = Path(receipt_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    return StageReceipt.model_validate(payload)
