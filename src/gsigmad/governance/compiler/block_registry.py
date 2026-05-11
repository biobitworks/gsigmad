"""
Named block registry for metaprompt compilation — FRM-02.

Maps governance block names to their file path templates and token budgets.
Block budgets from D-04 (locked). Registry format from D-01 (Python dict, per _REQUIRED_POWER_FIELDS pattern).
"""

# Context window and budget limit (D-04)
CONTEXT_WINDOW: int = 200_000   # Claude Sonnet / GPT-4 context window
CONTEXT_BUDGET_FRACTION: float = 0.60  # max governance overhead before task prompt

# Named block registry (D-01, D-02)
# Each entry: path_template (str), max_tokens (int), required (bool)
BLOCK_REGISTRY: dict = {
    "MISSION_ANCHOR": {
        "path_template": ".agent/MISSION_ANCHOR.md",
        "max_tokens": 500,
        "required": True,
    },
    "CHAIN_DIGEST": {
        "path_template": ".agent/CHAIN_DIGEST.md",
        "max_tokens": 1000,
        "required": False,  # may not exist on first experiment
    },
    "CANON_CORE": {
        "path_template": "src/gsigmad/governance/CANON-CORE-compact.md",
        "max_tokens": 800,
        "required": True,
    },
    "project_extension": {
        "path_template": "{project_root}/CANON.md",
        "max_tokens": 400,
        "required": False,
    },
}
