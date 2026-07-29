# Demo Release Report

## Version

`0.21.1-demo`

## Result

- Demo HTTP service works without Telegram credentials, PostgreSQL or external APIs.
- Mobile-first analytical page exposes the Sprint 15–20 workflow.
- `/health`, `/api/demo`, JSON and PDF artifact routes were checked over HTTP.
- Standalone HTML is included for direct opening on a smartphone.
- Production mode remains available through `APP_MODE=production`.

## Verification

- compileall: passed
- pytest: 88 passed
- HTTP smoke test: passed
- Docker configuration: included; Docker CLI was unavailable in the build environment, therefore an actual image build was not executed here.

## Public deployment

`render.yaml` provides a Docker web-service definition with `/health`. The public URL is created by the hosting provider after the repository is connected.
