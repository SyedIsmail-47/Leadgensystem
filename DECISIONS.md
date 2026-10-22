# DECISIONS

## D1 — Product rename
LeadForge → Leadgensystem (folder, DB name, docs). Stack unchanged.

## D2 — Runtime SaaS config
Niche, location, offer, sender, and scoring weights are DB-backed profiles selected per campaign. `.env` holds secrets/infra only.

## D3 — Auth
Streamlit session login with bcrypt hashes. Caddy provides HTTPS only (no basic auth).

## D4 — Multi-user ready
`workspaces` + `users` + `workspace_id` on owned tables. Single seeded admin for v1.
