# Leadgensystem RUNBOOK

## Prerequisites
- Docker + Docker Compose on Ubuntu VPS (Hostinger) or local Docker Desktop
- Copy `.env.example` → `.env` and set `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `SECRET_KEY`, `BASE_URL`

## Start (dev / single host)
```bash
cp .env.example .env
# edit secrets
docker compose up -d db
# wait healthy, then:
docker compose up -d --build worker dashboard
```
Dashboard: http://localhost:8501  
Login: `ADMIN_EMAIL` / `ADMIN_PASSWORD` (default `admin@local` / `change_me`)

## Start with HTTPS (prod profile)
Set `DOMAIN=your.domain.com` for Caddy, then:
```bash
docker compose --profile prod up -d --build
```
Caddy terminates TLS and reverse-proxies to the dashboard. App login is required (no Caddy basic auth).

## Stop
```bash
docker compose down
# keep data:
docker compose down   # volume pgdata retained
# wipe data:
docker compose down -v
```

## Add a campaign
1. Sign in → **Settings** → create Offer Profile (seeded example exists) and Sender Profile.
2. For email later: set physical address + SMTP → **Send test email** until verified.
3. **Campaign Builder**: niches → locations → filters → sources → scoring → offer/sender → schedule.
4. **Save & Run now**, or **Campaigns → Run now**.

## Pipeline
- Discovery (Google Maps, OSM fallback) → Enrichment → Scoring → Approve → Outreach sequence → SMTP send
- Worker schedules: discover hourly (cron’d campaigns), enrich every 15m, score every 20m, send every 10m

## Logs
```bash
docker compose logs -f worker
docker compose logs -f dashboard
docker compose exec db psql -U leadgensystem -d leadgensystem -c "SELECT id,job,status,found,errors FROM runs ORDER BY id DESC LIMIT 20;"
```
Or open **Runs & Logs** in the dashboard.

## Unsubscribe
Tokens are signed with `SECRET_KEY`. Link format: `{BASE_URL}/unsubscribe?token=...`  
Serve the FastAPI app in front of `/unsubscribe` or add a Caddy route to `uvicorn outreach.unsubscribe:create_app --factory`.

Quick local unsubscribe service:
```bash
PYTHONPATH=. uvicorn outreach.unsubscribe:create_app --factory --port 8080
```

## Known limitations
- Google Maps may captcha/block; runs mark `blocked` and OSM fallback is used when enabled.
- Meta/Google ads scrapers are soft stubs (signals only); do not block the pipeline.
- Playwright is serial (one browser job) to fit small VPS RAM.
- SMTP port 587 may be blocked on some VPS; use an external relay and keep sending disabled until SMTP test passes.
- Single seeded admin; no signup/billing UI.
- Reply detection is manual (“Mark replied”); IMAP is not implemented.

## Acceptance smoke
```bash
docker compose up -d db
psql $DATABASE_URL -c '\dt'
PYTHONPATH=. python -m scrapers.gmaps "dentist" "Lahore" 20
PYTHONPATH=. python -c "from enrich.pipeline import enrich_pending; print(enrich_pending(1,20))"
PYTHONPATH=. python -c "from scoring.engine import score_pending; print(score_pending(1))"
PYTHONPATH=. pytest -q
```
