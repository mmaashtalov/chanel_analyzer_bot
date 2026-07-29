# Sprint 20 Report — Temporal Claim Tracking

## Version

0.21.0

## Implemented

- Stable claim identity inside a Workspace.
- Claim timeline across provenance bundles.
- Relations: supports, updates, supersedes, contradicts.
- Temporal lifecycle: current, superseded, contradicted, resolved.
- SHA-256 event hashes and timeline integrity hash.
- Telegram commands: `/claim_timeline_build`, `/claim_timeline`, `/claim_timeline_report`.
- PDF/JSON timeline exports.
- Alembic migration 0016.

## Validation

- 84 tests passed.
- compileall passed.
- one Alembic head.

## Limitations

- Relation classification is deterministic and explainable, but conservative.
- Cross-language paraphrases and implicit contradictions may require a future optional semantic processor.
- Temporal resolution does not infer external causality.
