---
name: gsigmad-session-pause
description: "Pause current session and save state for resumption. Use when interrupting a session mid-experiment. Saves conversation digest, updates SESSION_LOG, and runs signature lint before optional commit."
disable-model-invocation: true
allowed-tools: Read, Write, Bash
---

# Session Pause ($session-orchestrator + $change-log-compliance)

Session pausing. Complete the SESSION PAUSE checklist before stopping.

## Agent Self-Identification

- Author: Claude Code | Agent/Version: claude-sonnet-4-6 | Software: Claude Code
- Signature format: SIG-YYYYMMDDTHHMMSSZ-claude-[hash4]

## SESSION PAUSE CHECKLIST

1. Update <workspace>/SESSION_LOG.md with:
   - Accomplishments so far, Files changed, Status: "(paused)", SIGNATURE ID
2. Update ALL modified document Change Logs (SIGNATURE ID REQUIRED):
   | Sig ID | Timestamp | Author | Agent/Version | Software | Summary |
3. Update `.agent/task.md` to reflect: [x] Completed, [/] In-progress, [ ] Remaining
4. **PROMPT INTEGRITY CHECK** (REQUIRED):
   a. For each PROMPT number allocated this session, verify MD + JSON files exist in `prompts/`
   b. Verify PROMPT_EXP_MAP.md has been updated with any new entries
   c. Verify `next_prompt.txt` and `next_exp.txt` match actual state
   d. If any file is missing: CREATE it now (even as Draft) before pausing
   e. Report: "PROMPT integrity: {N} PROMPTs allocated, {N} files verified, map updated"
5. **CONVERSATION DIGEST** (MANDATORY):
   a. Create `.agent/conversation_digests/YYYYMMDD_HHMMSS.md`
   b. Include: PI Intent Summary (use exact PI words), Goal Evolution (did PI refine/redirect thesis?),
      Decisions Made (why not what), Drift Corrections (how many times PI restated goal), Open Questions
   c. If PI restated the goal during this session, flag with exact quotes and count
   d. Report: "Conversation digest: CREATED at {path}"
6. Update daily journal with pause entry (SIGNATURE REQUIRED).
7. **Artifact Provenance** (if significant work done):
   - Copy session transcript to `provenance/claude_artifacts/YYYY-MM-DD_<label>/`
   - Source: `~/.claude/projects/<project-slug>/<session-uuid>.jsonl`
   - Create PROVENANCE.md (session metadata, files copied, experiments touched)
   - Create session_summary.md (key decisions, insights, experiments)
   - Update `provenance/claude_artifacts/CLAUDE_INDEX.md`
   - Rules: `research_hub/portfolio/ARTIFACT_PROVENANCE_RULES.md`
8. Run signature lint on all modified files:
   - Search for SIG- patterns
   - Verify each matches: ^SIG-[0-9]{8}T[0-9]{6}Z-[a-z0-9]{2,12}-[0-9a-f]{4}$
   - If any fail: normalize and record old_sig -> new_sig mapping
9. If user approves: stage and commit per repo.
10. Do NOT push unless user explicitly approves.

## Report Back

- Documents updated with Change Log entries (list paths)
- task.md status (X completed / Y in progress / Z remaining)
- Artifact provenance: copied to provenance/<app>_artifacts/ (or "skipped - no significant work")
- Signature lint status + any old_sig -> new_sig mappings
- Commit hash (if committed) or "not committed"
- Pending work items for next session
