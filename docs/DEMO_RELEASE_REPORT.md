# Demo Release Report

## Version

`0.22.0-demo`

## Result

- Demo HTTP service works without Telegram credentials, PostgreSQL or external APIs.
- Mobile-first analytical page exposes the current evidence-first workflow.
- `/health`, `/api/demo`, JSON and PDF artifact routes were checked over HTTP.
- Standalone HTML is included for direct opening on a smartphone.
- Production mode remains available through `APP_MODE=production`.

## Verification

- compileall: passed
- pytest: the reproducible count is stored in `MANIFEST.json`
- HTTP smoke test: passed
- Docker configuration: included; local Docker CLI is environment-dependent, so image build must be подтверждён CI.

## Public deployment

`render.yaml` provides a Docker web-service definition with `/health`. The public URL is created by the hosting provider after the repository is connected.
