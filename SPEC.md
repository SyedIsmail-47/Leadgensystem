# SPEC.md: Leadgensystem

## 1. Stack (fixed; do not substitute)
| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| DB | PostgreSQL 16 (plain SQL migrations in `db/init.sql`, access via `psycopg[pool]`) |
| Scraping | Playwright (Chromium, headless), `httpx` + `selectolax` for static pages |
| Validation | `email-validator`, `dnspython` (MX), `phonenumbers` |
| Scheduler | APScheduler running inside the worker container |
| Dashboard | Streamlit (multipage), `pandas`, `plotly` |
| Email | `smtplib` over SMTP (port 587 relay), Jinja2 templates |
| Proxy/HTTPS | Caddy (HTTPS reverse proxy; app owns auth) |
| Infra | Docker Compose on one Hostinger VPS |

## 2. Product model
Single-user SaaS style: Campaign Builder chooses niches/locations/filters/sources/scoring/offer/sender at runtime.
Settings hold Offer Profiles, Sender Profiles, Scoring Profiles. Multi-user ready via `users` + `workspace_id`.

## 3. Repo layout
See PLAN.md. Root folder: `Leadgensystem/`.

## 4. Schema
See `db/init.sql`. Core tables from original LeadForge SPEC plus workspaces, users, settings, offer/sender/scoring profiles, campaign_niches, campaign_locations.

## 5. Modules
Discovery (`scrapers/gmaps.py` + `osm.py`), enrichment (`website.py` + `enrich/`), scoring (`scoring/`), outreach (`outreach/`), worker (`worker/`), dashboard (`dashboard/`).

## 6. Scoring (default weights)
Fit 40 / Intent 30 / Reachability 30 as in original SPEC. Overridable per campaign via `scoring_profiles`.

## 7. Milestones
M1–M7 as in PLAN.md.

## 8. Environment (`.env.example`)
Secrets/infra only: `POSTGRES_*`, `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SECRET_KEY`, `BASE_URL`, `DEFAULT_REGION`.
