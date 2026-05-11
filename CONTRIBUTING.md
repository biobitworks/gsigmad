# Contributing

`gsigmad` is a public release of reusable science-governance tooling.

## Ground Rules

- Keep public examples generic.
- Do not add private project adapters, raw experiment data, credentials, patient data, gated datasets, or internal operator receipts.
- Missing integrations must be reported as `not_configured`, not PASS.
- New scientific workflows must preserve preregistration, claim-audit, and no-writeback boundaries.

## Development

```bash
uv sync --all-extras
uv run pytest
```

Open a pull request with:

- a short description of the governance behavior changed
- tests for new gates or command behavior
- notes on whether any public/private boundary changed
