"""Tests for MCP server tool registration and behavior."""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import yaml


def test_mcp_server_import_without_fastmcp():
    """Importing mcp_server without fastmcp raises SystemExit with helpful message."""
    # Remove cached module if present
    mod_name = "gsigmad.mcp_server"
    saved = sys.modules.pop(mod_name, None)
    try:
        with patch.dict("sys.modules", {"fastmcp": None}):
            import importlib

            with pytest.raises(SystemExit, match="FastMCP"):
                importlib.import_module(mod_name)
    finally:
        # Restore
        sys.modules.pop(mod_name, None)
        if saved is not None:
            sys.modules[mod_name] = saved


# --- Tests below only run if fastmcp is available ---
fastmcp = pytest.importorskip("fastmcp")

from gsigmad.mcp_server import mcp  # noqa: E402


def test_mcp_instance_name():
    """FastMCP server is named 'gsigmad'."""
    assert mcp.name == "gsigmad"


def test_mcp_tool_count():
    """At least 11 core tools registered including continuation inspection."""
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) >= 11, f"Only {len(tools)} tools registered, expected >=11"


def test_mcp_tool_names_prefixed():
    """All tool names start with gsigmad_ per D-08."""
    tools = asyncio.run(mcp.list_tools())
    for tool in tools:
        assert tool.name.startswith("gsigmad_"), f"Tool {tool.name} missing gsigmad_ prefix"


def test_mcp_required_tools_present():
    """All required core MCP tools are registered."""
    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}
    required = {
        "gsigmad_init",
        "gsigmad_ollarma_continuation",
        "gsigmad_register",
        "gsigmad_run",
        "gsigmad_audit",
        "gsigmad_status",
        "gsigmad_redteam",
        "gsigmad_export",
        "gsigmad_drift",
        "gsigmad_classify",
        "gsigmad_power",
    }
    missing = required - tool_names
    assert not missing, f"Missing required MCP tools: {missing}"


def test_mcp_tools_have_project_path_param():
    """Every MCP tool function has project_path parameter with default '.' per D-09."""
    from gsigmad import mcp_server

    tool_funcs = [
        mcp_server.gsigmad_init,
        mcp_server.gsigmad_ollarma_continuation,
        mcp_server.gsigmad_register,
        mcp_server.gsigmad_run,
        mcp_server.gsigmad_audit,
        mcp_server.gsigmad_status,
        mcp_server.gsigmad_redteam,
        mcp_server.gsigmad_export,
        mcp_server.gsigmad_drift,
        mcp_server.gsigmad_classify,
        mcp_server.gsigmad_power,
    ]
    for fn in tool_funcs:
        sig = inspect.signature(fn)
        assert "project_path" in sig.parameters, (
            f"{fn.__name__} missing project_path parameter"
        )
        assert sig.parameters["project_path"].default == ".", (
            f"{fn.__name__} project_path default is not '.'"
        )


def test_mcp_init_tool_returns_agent_hints(tmp_path):
    """gsigmad_init MCP tool returns dict with agent_hints per D-13."""
    from gsigmad.mcp_server import gsigmad_init

    result = gsigmad_init(project_path=str(tmp_path))
    assert isinstance(result, dict)
    assert "agent_hints" in result
    assert isinstance(result["agent_hints"], dict)
    assert "next_tools" in result["agent_hints"]


def test_mcp_status_tool_returns_agent_hints(tmp_path):
    """gsigmad_status MCP tool returns dict with agent_hints per D-13."""
    from gsigmad.mcp_server import gsigmad_init, gsigmad_status

    # Init first so status has something to work with
    gsigmad_init(project_path=str(tmp_path))
    result = gsigmad_status(project_path=str(tmp_path))
    assert isinstance(result, dict)
    assert "agent_hints" in result


def test_mcp_ollarma_continuation_returns_structured_payload(tmp_path: Path):
    """Continuation inspection reads the task section and returns structured data."""
    from gsigmad.mcp_server import gsigmad_ollarma_continuation

    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    (agent_dir / "OLLARMA_CONTINUATION.md").write_text(
        "# Ollarma Continuation Policy\n",
        encoding="utf-8",
    )
    task_path = agent_dir / "task.md"
    task_path.write_text(
        """# Current Task

## Scope

Bounded follow-up.

## Objectives

- [ ] Finish the local bounded task

## Ollarma Continuation

Suitable: yes
Command: ollarma workflow run --manifest .agent/task.md

Expected artifacts:
- .agent/receipts/ollarma.json
- reports/summary.md

Stop condition: both artifacts exist
Human resume command: gsigmad status

No-overlap guards:
- do not modify .planning/
""",
        encoding="utf-8",
    )

    result = gsigmad_ollarma_continuation(project_path=str(tmp_path))
    assert result["policy_present"] is True
    assert result["task_present"] is True
    assert result["suitable"] is True
    assert result["task_fields"] == {
        "command": "ollarma workflow run --manifest .agent/task.md",
        "expected_artifacts": [
            ".agent/receipts/ollarma.json",
            "reports/summary.md",
        ],
        "stop_condition": "both artifacts exist",
        "no_overlap_guards": ["do not modify .planning/"],
        "human_resume_command": "gsigmad status",
    }
    assert result["missing_fields"] == []
    assert "agent_hints" in result


def test_mcp_register_rejects_opted_in_anchor_projects_without_anchor_support(tmp_path: Path):
    """Legacy MCP register must not silently bypass anchor enforcement for opted-in projects."""
    from gsigmad.mcp_server import gsigmad_init, gsigmad_register

    gsigmad_init(project_path=str(tmp_path))
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["anchor_schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = gsigmad_register(
        exp_type="exploratory",
        title="Anchor guarded",
        hypothesis="MCP should not bypass opt-in anchor enforcement.",
        project_path=str(tmp_path),
    )

    assert "error" in result
    assert "anchor" in result["error"].lower()
    assert not list((tmp_path / ".gsigmad" / "experiments").glob("EXP-*.yaml"))
