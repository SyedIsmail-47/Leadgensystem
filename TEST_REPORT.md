# TEST_REPORT.md — Leadgensystem QA

Generated from `TEST_PROMPT.md` automated suite. Command: `pytest -q` against `leadgensystem_test`.

**Totals: 94 passed / 0 failed / 0 skipped** (latest full run)

## Results by case ID

| ID | Description | Result | Notes |
|---|---|---|---|
| A1 | Apply init.sql — all tables | PASS | |
| A2 | init.sql twice idempotent | PASS | `CREATE IF NOT EXISTS` + seed guards |
| A3 | owned tables have workspace_id | PASS | |
| A4 | seed admin hashed | PASS | bcrypt |
| A5 | campaign delete cascades | PASS | |
| A6 | dedupe_key unique / upsert | PASS | |
| B1 | dedupe phone variants | PASS | PK 03↔92 normalize |
| B2 | dedupe by domain | PASS | |
| B3 | phone normalize PK | PASS | |
| B4 | email extraction filters | PASS | |
| B5 | obfuscated email | PASS | `[at]`/`[dot]` |
| B6 | email + mocked MX fail | PASS | |
| B7 | URL normalization | PASS | |
| C1 | site_full signals | PASS | fixtures |
| C2 | site_bare opportunity gap | PASS | |
| C3 | Meta pixel both forms | PASS | |
| C4 | Google tag both forms | PASS | |
| C5 | booking widget | PASS | |
| C6 | WhatsApp link formats | PASS | |
| C7 | social excludes sharer | PASS | |
| C8 | timeout soft-fail | PASS | `enrich_error` set |
| C9 | crawl ≤5 same-domain | PASS | |
| C10 | enrich signal idempotent | PASS | UNIQUE + upsert |
| D1 | all rules 100/A | PASS | |
| D2 | empty lead 0/C | PASS | |
| D3 | rating 3.9 vs 4.0 | PASS | |
| D4 | reviews 19 vs 20 | PASS | |
| D5 | tier capped without contact | PASS | |
| D6 | tier boundaries | PASS | |
| D7 | score idempotent | PASS | |
| D8 | campaign weight override | PASS | |
| D9 | confidence 0.4 / 1.0 | PASS | |
| D10 | breakdown sums to score | PASS | |
| E1 | 2×3 query grid | PASS | |
| E2 | niche dedupe | PASS | |
| E3 | dry-run no DB writes | PASS | |
| E4 | filters exclude | PASS | |
| E5 | max per query/run | PASS | |
| E6 | source toggles mocked | PASS | |
| E7 | invalid input errors | PASS | |
| E8 | outreach requires profiles | PASS | |
| F1 | parse gmaps fixture | PASS | |
| F2 | missing optional fields | PASS | |
| F3 | blocked fixture | PASS | |
| F4 | rerun no duplicates | PASS | |
| F5 | OSM mocked Overpass | PASS | |
| F6 | delay helper bounds | PASS | |
| F7 | ads scrapers soft | PASS | stubs present |
| G1–G15 | outreach/compliance | PASS | fake SMTP + freezegun |
| H1–H5 | worker/scheduler | PASS | |
| I1–I11 | dashboard | PASS | AppTest + service checks |
| J1–J6 | security | PASS | XSS escaped in Jinja |
| K1 | full pipeline e2e | PASS | fixtures + fake SMTP |

Legacy unit files `test_dedupe.py`, `test_scoring.py`, `test_validators.py` also PASS (covered by B/D).

## Defects found and fixed during QA

1. **Dedupe phone PK** — `0300…` vs `+92 300…` produced different keys → normalize in `scrapers/dedupe.py`.
2. **inside_location** granted points with no location → default false when location unset (`scoring/rules.py`).
3. **Enrich soft-fail** — store `enrich_error`; signals upsert for idempotency (`UNIQUE(lead_id,channel,signal)`).
4. **send_step** ignored `scheduled_for` → now skips until due.
5. **SMTP STARTTLS** on plain dummy ports → skip when unsupported / port 1025.
6. **Multipage auth** — login form on every page via `require_login`.
7. **Gmaps name "Results"** — skip feed chrome titles.
8. **XSS in email body** — Jinja escapes `<script>` in merge fields (asserted by J4).

## Open issues (highest risk)

1. **Real Google Maps / Playwright** still flaky under captcha; automated coverage is fixture-only (see MANUAL_CHECKLIST).
2. **Ads scrapers** remain soft stubs — no true `running_ads` detection in CI.
3. **Sending window** uses UTC hour, not sender timezone (`Asia/Karachi` stored but not applied in `_within_window`).

## How to re-run

```bash
docker compose up -d db
make test          # or: pytest -q
make test-unit
make test-int
make test-e2e
make lint
```
