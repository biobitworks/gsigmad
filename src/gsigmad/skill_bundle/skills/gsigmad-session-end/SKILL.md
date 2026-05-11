---
name: gsigmad-session-end
description: "End current session with final state save and lab notebook commit. Use when completing a work session. Runs blocking PROMPT integrity check, saves conversation digest, and requires artifact provenance before closing."
disable-model-invocation: true
allowed-tools: Read, Write, Bash
---

# Session End ($session-orchestrator + $change-log-compliance)

Session ending. Complete the SESSION END checklist before stopping.

## Agent Self-Identification

- Author: Claude Code | Agent/Version: claude-sonnet-4-6 | Software: Claude Code
- Signature format: SIG-YYYYMMDDTHHMMSSZ-claude-[hash4]

## SESSION END CHECKLIST

1. Update <workspace>/SESSION_LOG.md with:
   - End timestamp, Duration, Final accomplishments, All files changed, Pending items, SIGNATURE ID
2. Update ALL modified document Change Logs (SIGNATURE ID REQUIRED).
3. Update `.agent/task.md` to reflect final session state.
4. **PROMPT INTEGRITY CHECK** (REQUIRED — BLOCKING):
   a. For each PROMPT number allocated this session, verify MD + JSON files exist in `prompts/`
   b. Verify PROMPT_EXP_MAP.md has been updated with all new entries from this session
   c. Verify `next_prompt.txt` and `next_exp.txt` match actual state after this session
   d. If any file is missing: CREATE it now (even as Draft) — DO NOT skip
   e. For ChatGPT/external prompts: verify stored as EXTREF-### in `external_research/` with prompt.md + ingestion_notes.md, REGISTRY.md updated, `next_extref.txt` correct
   f. Report: "PROMPT integrity: {N} PROMPTs allocated, {N} files verified, map updated, counters correct"
   g. Report: "EXTREF integrity: {N} EXTREFs allocated, {N} folders verified, REGISTRY updated, counter correct"
   h. **If integrity check fails, DO NOT proceed to commit until resolved**
5. **CONVERSATION DIGEST** (MANDATORY):
   a. Create `.agent/conversation_digests/YYYYMMDD_HHMMSS.md`
   b. Include: PI Intent Summary (use exact PI words), Goal Evolution (did PI refine/redirect thesis?),
      Decisions Made (why not what), Drift Corrections (how many times PI restated goal), Open Questions
   c. If PI restated the goal during this session, flag with exact quotes and count
   d. Report: "Conversation digest: CREATED at {path}"
6. Add session synthesis entry to LAB_NOTEBOOK.md:
   ### Session Synthesis: [DATE]
   **Session ID**: [SESSION_ID]
   **Signature ID**: [SIG_ID]
   **Experiments**: EXP-### (list completed)
   **Prompts**: PROMPT-### (list created/updated)
   **Key Accomplishments**: (bullet list)
   **Pending Items**: (bullet list for next session)
7. Update daily journal with session end timestamp and summary (SIGNATURE REQUIRED).
8. **Artifact Provenance** (REQUIRED at session end):
   - Copy session transcript to `provenance/claude_artifacts/YYYY-MM-DD_<label>/`
   - Source: `~/.claude/projects/<project-slug>/<session-uuid>.jsonl`
   - Create PROVENANCE.md (session metadata, files copied, experiments touched, SHA256 for large files)
   - Create session_summary.md (key decisions, insights, experiments)
   - Update `provenance/claude_artifacts/CLAUDE_INDEX.md`
   - Rules: `research_hub/portfolio/ARTIFACT_PROVENANCE_RULES.md`
   - NOTE: For Codex sessions, source is `~/.codex/<session-dir>/`; dest is `provenance/codex_artifacts/`
   - NOTE: For ChatGPT sessions, manually export JSON from UI; dest is `provenance/chatgpt_artifacts/`
9. Run signature lint on all modified files; normalize non-canonical SIG IDs.
10. If user approves: stage and commit per repo.
11. If user approves: push to remote per repo.

## Report Back

- Documents updated with Change Log entries (list paths)
- LAB_NOTEBOOK synthesis entry (brief summary)
- Artifact provenance: copied to provenance/<app>_artifacts/ (list files, sizes)
- Signature lint status + any old_sig -> new_sig mappings
- Commit hash and push status
- Pending items for next session
