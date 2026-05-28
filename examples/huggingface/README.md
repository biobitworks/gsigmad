# Hugging Face Artifacts

This directory contains public-safe templates for optional Hugging Face release
surfaces:

- `dataset/` is a dataset-card template plus synthetic JSONL gate-trace rows.
- `space/` is a static Space template that visualizes the same gate-trace
  boundary without requiring a Python runtime.

These artifacts are examples, not a full benchmark release. The synthetic rows
document the shape of deterministic gate evidence and known missing-gate
categories without exposing private projects, private fixtures, or raw research
data.
