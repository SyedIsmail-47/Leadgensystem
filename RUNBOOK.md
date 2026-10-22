# Leadgensystem RUNBOOK

## Prerequisites
- Ubuntu VPS (Hostinger KVM / VPS) with root or sudo
- Docker Engine + Docker Compose plugin
- No domain required for this path (use the VPS public IP)

---

## No-domain Hostinger VPS deploy (recommended for now)

### 1. Create / open the VPS
1. Hostinger → VPS → note the **public IPv4** (example: `203.0.113.10`).
2. SSH in:
   ```bash
   ssh root@YOUR_VPS_IP
   ```

### 2. Install Docker (Ubuntu)
```bash
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
docker --version
docker compose version
```

### 3. Clone the repo
```bash
cd /opt
git clone https://github.com/SyedIsmail-47/Leadgensystem.git
cd Leadgensystem
```

### 4. Create `.env` (no domain)
```bash
cp .env.example .env
nano .env
```

Set at least:
```env
POSTGRES_PASSWORD=pick_a_long_random_password
DATABASE_URL=postgresql://leadgensystem:pick_a_long_random_password@db:5432/leadgensystem
ADMIN_EMAIL=admin@local
ADMIN_PASSWORD=pick_a_strong_login_password
SECRET_KEY=pick_another_long_random_string
BASE_URL=http://YOUR_VPS_IP:8080
DEFAULT_REGION=PK
```

Notes:
- `BASE_URL` points at the **unsubscribe** service (`:8080`), not Streamlit. Email footers use this.
- Dashboard URL is separate: `http://YOUR_VPS_IP:8501`
- Do **not** commit `.env`

Generate secrets quickly:
```bash
openssl rand -hex 24
```

### 5. Firewall (Hostinger + UFW)
Open only what you need. **Do not** open Postgres `5432` publicly.

```bash
ufw allow OpenSSH
ufw allow 8501/tcp   # Streamlit dashboard
ufw allow 8080/tcp   # unsubscribe API
ufw enable
ufw status
```

Also check Hostinger hPanel → VPS → Firewall / Security and allow **8501** and **8080** if an external firewall is on.

### 6. Start the stack
First build can take several minutes (Playwright Chromium).

```bash
docker compose up -d --build db worker dashboard unsub
docker compose ps
docker compose logs -f dashboard
```

Wait until dashboard logs show it is listening, then open:

| Service | URL |
|---|---|
| Dashboard | `http://YOUR_VPS_IP:8501` |
| Unsubscribe API | `http://YOUR_VPS_IP:8080/unsubscribe?token=...` |

Login: `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

### 7. Smoke check on the VPS
```bash
docker compose exec -T db psql -U leadgensystem -d leadgensystem -c '\dt'
docker compose logs --tail 50 worker
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8501/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/docs
```

### 8. First-time product setup
1. Settings → confirm Offer Profile (seeded) and Scoring Profile.
2. Settings → create **Sender Profile** (physical address + SMTP). Sending stays off until SMTP test passes.
3. Campaign Builder → create a small campaign → **Save & Run now**.
4. Leads → review scores → Outreach when ready.

### 9. Updates later
```bash
cd /opt/Leadgensystem
git pull
docker compose up -d --build worker dashboard unsub
```

### 10. Stop / wipe
```bash
docker compose down          # keep Postgres volume
docker compose down -v       # DESTROYS database
```

### No-domain limitations
- Browser will warn that the site is not HTTPS (expected on raw IP).
- When you buy a domain later: point DNS A record to the VPS IP, set `BASE_URL=https://your.domain`, then:
  ```bash
  # in .env also set DOMAIN=your.domain.com for Caddy
  docker compose --profile prod up -d --build
  ```
- Prefer not to leave `8501` open forever on a public IP without HTTPS; add domain + Caddy when you can.

---

## Local Docker Desktop (dev)
```bash
cp .env.example .env
# DATABASE_URL host can stay @db for compose; for host tools use @localhost
docker compose up -d --build db worker dashboard unsub
```
Dashboard: http://localhost:8501

## Start with HTTPS (when you have a domain)
Set `DOMAIN=your.domain.com` and `BASE_URL=https://your.domain.com`, then:
```bash
docker compose --profile prod up -d --build
```
Caddy terminates TLS and reverse-proxies dashboard + `/unsubscribe`.

## Add a campaign
1. Sign in → **Settings** → Offer Profile + Sender Profile.
2. Sender: physical address + SMTP → **Send test email** until verified.
3. **Campaign Builder** → Save & Run now (or Campaigns → Run now).

## Pipeline
Discovery → Enrichment → Scoring → Approve → Outreach (SMTP).  
Worker: discover (cron’d campaigns hourly), enrich 15m, score 20m, send 10m.

## Logs
```bash
docker compose logs -f worker
docker compose logs -f dashboard
docker compose exec db psql -U leadgensystem -d leadgensystem -c "SELECT id,job,status,found,errors FROM runs ORDER BY id DESC LIMIT 20;"
```

## Known limitations
- Google Maps may captcha/block; run status `blocked`; OSM fallback when enabled.
- Ads scrapers are soft stubs.
- Playwright is serial (small VPS RAM).
- SMTP 587 may be blocked on some VPS — use an external relay.
- Single seeded admin; manual “Mark replied”.

## Acceptance smoke (dev machine with DB)
```bash
docker compose up -d db
pytest -q
```
