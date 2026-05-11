# Security Policy

## Reporting

Please report security issues privately through the repository security advisory
flow when available. Do not open a public issue containing credentials,
private project paths, patient data, controlled-access data, or exploit details.

## Public Release Boundary

This repository must not contain:

- API keys, tokens, passwords, SSH keys, or database URLs with credentials
- private project adapters
- raw sequences, row-level experiment data, patient data, or controlled-access records
- internal dashboard exports or live writeback receipts

If a safety scan finds any of these, treat the release as blocked until the
artifact is removed and the repository history is reviewed.
