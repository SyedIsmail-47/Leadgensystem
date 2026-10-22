# MANUAL_CHECKLIST.md — Leadgensystem

Human-only checks (section L). Do not automate.

- [ ] Real Google Maps run: 1 niche × 1 city, 10 leads. Spot-check 5 against the live listings.
- [ ] If Maps shows a captcha, confirm the run ends `blocked` with the banner and the OSM fallback works.
- [ ] Real SMTP "Send test email" to my own inbox; check it is not in spam; check SPF/DKIM pass in the headers.
- [ ] Click the unsubscribe link in that email and confirm suppression.
- [ ] Fresh Ubuntu VPS: follow `RUNBOOK.md` exactly; `docker compose up -d` succeeds; HTTPS and login work.
- [ ] Check VPS memory during a Playwright run (`docker stats`); no OOM kills.
- [ ] Confirm outbound port 587 works from the VPS.
- [ ] Visually compare the dashboard with `DESIGN.md` (tier chips, score bars, funnel chart).
