# Architecture Review before Sprint 21

## Verdict

Sprint 21 is justified only if it improves operational trust, not feature count.

## Recommended focus

**Contradiction Triage & Resolution Workflow**

1. Queue unresolved contradictions by severity and confidence.
2. Analyst decisions: confirm contradiction, mark compatible, resolve with newer claim, request evidence.
3. Immutable resolution events.
4. Recalculate temporal status and current canonical claim.
5. Telegram-first triage and resolution.
6. PDF/JSON contradiction dossier.

## Explicitly deferred

- Graph database.
- LLM-only contradiction decisions.
- New frontend.
- Microservice split.
