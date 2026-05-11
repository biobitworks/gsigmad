"""Read Ollarma continuation policy/task state from a workspace."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

_TASK_FIELDS = (
    "command",
    "expected_artifacts",
    "stop_condition",
    "no_overlap_guards",
    "human_resume_command",
)

_FIELD_LABELS = {
    "command": ("command", "exact command"),
    "expected_artifacts": ("expected artifacts", "expected artifact paths"),
    "stop_condition": ("stop condition", "success condition"),
    "no_overlap_guards": ("no-overlap guards", "no overlap guards"),
    "human_resume_command": ("human resume command", "resume command"),
}

_SECTION_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+.*ollarma continuation.*$", re.IGNORECASE)
_GENERIC_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_FIELD_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?P<label>[^:]+?)\s*:\s*(?P<value>.*)$")
_BULLET_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?P<value>.*)$")


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _strip_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"`", '"', "'"}:
        return text[1:-1].strip()
    return text


def _split_list_value(value: str) -> list[str]:
    items: list[str] = []
    for chunk in re.split(r"[\n;,]+", value):
        item = _strip_value(chunk).strip()
        if item:
            items.append(item)
    return items


def _select_task_section(lines: list[str]) -> list[str]:
    for index, line in enumerate(lines):
        if _SECTION_HEADING_RE.match(line):
            section: list[str] = []
            for candidate in lines[index + 1 :]:
                if _GENERIC_HEADING_RE.match(candidate):
                    break
                section.append(candidate)
            return section
    return lines


def _is_field_line(line: str) -> tuple[str | None, str]:
    match = _FIELD_LINE_RE.match(line)
    if not match:
        return None, ""
    label = _normalize_label(match.group("label"))
    value = match.group("value").strip()
    for field, aliases in _FIELD_LABELS.items():
        for alias in aliases:
            alias_norm = _normalize_label(alias)
            if label == alias_norm or label.startswith(f"{alias_norm} "):
                return field, value
    return None, ""


def _parse_task_fields(task_text: str) -> dict[str, Any]:
    lines = _select_task_section(task_text.splitlines())
    buffers: dict[str, list[str]] = {field: [] for field in _TASK_FIELDS}
    current_field: str | None = None

    for line in lines:
        if _GENERIC_HEADING_RE.match(line):
            current_field = None
            continue

        field, value = _is_field_line(line)
        if field:
            current_field = field
            if value:
                buffers[field].append(value)
            continue

        if current_field is None:
            continue

        if not line.strip():
            if buffers[current_field]:
                buffers[current_field].append("")
            continue

        bullet_match = _BULLET_RE.match(line)
        continuation = bullet_match.group("value").strip() if bullet_match else line.strip()
        if continuation:
            buffers[current_field].append(continuation)

    command = _strip_value("\n".join(part for part in buffers["command"] if part)).strip() or None
    stop_condition = (
        _strip_value("\n".join(part for part in buffers["stop_condition"] if part)).strip() or None
    )
    human_resume_command = (
        _strip_value(
            "\n".join(part for part in buffers["human_resume_command"] if part)
        ).strip()
        or None
    )
    expected_artifacts = _split_list_value("\n".join(buffers["expected_artifacts"]))
    no_overlap_guards = _split_list_value("\n".join(buffers["no_overlap_guards"]))

    return {
        "command": command,
        "expected_artifacts": expected_artifacts,
        "stop_condition": stop_condition,
        "no_overlap_guards": no_overlap_guards,
        "human_resume_command": human_resume_command,
    }


def load_ollarma_continuation(project_path: str | Path = ".") -> dict[str, Any]:
    """Return a structured Ollarma continuation payload for a workspace."""
    workspace_root = Path(project_path).resolve()
    policy_path = workspace_root / ".agent" / "OLLARMA_CONTINUATION.md"
    task_path = workspace_root / ".agent" / "task.md"

    policy_present = policy_path.is_file()
    task_present = task_path.is_file()
    task_fields = {
        "command": None,
        "expected_artifacts": [],
        "stop_condition": None,
        "no_overlap_guards": [],
        "human_resume_command": None,
    }

    if task_present:
        task_fields = _parse_task_fields(task_path.read_text(encoding="utf-8"))

    missing_fields = []
    if not policy_present:
        missing_fields.append("policy")
    if not task_present:
        missing_fields.append("task")

    for field in _TASK_FIELDS:
        value = task_fields[field]
        if field in {"expected_artifacts", "no_overlap_guards"}:
            if not value:
                missing_fields.append(field)
        elif not value:
            missing_fields.append(field)

    return {
        "workspace_path": str(workspace_root),
        "policy_path": str(policy_path),
        "task_path": str(task_path),
        "policy_present": policy_present,
        "task_present": task_present,
        "suitable": not missing_fields,
        "task_fields": task_fields,
        "missing_fields": missing_fields,
    }
