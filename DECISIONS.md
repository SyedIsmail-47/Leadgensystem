# DECISIONS

## D1 — Product rename
LeadForge → Leadgensystem (folder, DB name, docs). Stack unchanged.

## D2 — Runtime SaaS config
Niche, location, offer, sender, and scoring weights are DB-backed profiles selected per campaign. `.env` holds secrets/infra only.

## D3 — Auth
Streamlit session login with bcrypt hashes. Caddy provides HTTPS only (no basic auth).

## D4 — Multi-user ready
`workspaces` + `users` + `workspace_id` on owned tables. Single seeded admin for v1.

## D5 — Ads scrapers
Meta/Google ads modules are soft stubs that write unchecked signals only. Full Playwright Ad Library scraping cut for time/fragility; pipeline never blocks.

## D6 — SMTP password storage
Sender `smtp_pass_enc` stores the password as provided (single-user VPS). Encrypt-at-rest can be added later without schema rename.

## D7 — selectolax backend
Use `LexborHTMLParser` (selectolax 1.x deprecated Modest backend).
