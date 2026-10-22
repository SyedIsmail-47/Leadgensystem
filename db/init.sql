-- Leadgensystem schema (multi-user ready, idempotent)

CREATE TABLE IF NOT EXISTS workspaces (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'admin',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (workspace_id, key)
);

CREATE TABLE IF NOT EXISTS offer_profiles (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  pitch TEXT,
  pain_points TEXT[] DEFAULT '{}',
  gap_hook_rules JSONB DEFAULT '[]',
  templates JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sender_profiles (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  sender_name TEXT NOT NULL,
  company TEXT,
  from_email TEXT NOT NULL,
  reply_to TEXT,
  domain TEXT,
  physical_address TEXT,
  smtp_host TEXT,
  smtp_port INT DEFAULT 587,
  smtp_user TEXT,
  smtp_pass_enc TEXT,
  daily_limit INT DEFAULT 20,
  send_window_start INT DEFAULT 9,
  send_window_end INT DEFAULT 17,
  timezone TEXT DEFAULT 'UTC',
  smtp_verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scoring_profiles (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  weights JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaigns (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  niche TEXT,
  location TEXT,
  max_leads INT DEFAULT 100,
  schedule_cron TEXT,
  status TEXT DEFAULT 'active',
  offer_profile_id INT REFERENCES offer_profiles(id) ON DELETE SET NULL,
  sender_profile_id INT REFERENCES sender_profiles(id) ON DELETE SET NULL,
  scoring_profile_id INT REFERENCES scoring_profiles(id) ON DELETE SET NULL,
  filters JSONB DEFAULT '{}',
  sources JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaign_niches (
  id SERIAL PRIMARY KEY,
  campaign_id INT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  niche TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_locations (
  id SERIAL PRIMARY KEY,
  campaign_id INT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  country TEXT,
  city TEXT NOT NULL,
  area TEXT,
  radius_km NUMERIC(8,2)
);

CREATE TABLE IF NOT EXISTS campaign_presets (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  value JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leads (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT,
  address TEXT,
  city TEXT,
  phone TEXT,
  website TEXT,
  email TEXT,
  gmaps_url TEXT,
  rating NUMERIC(2,1),
  review_count INT,
  facebook_url TEXT,
  instagram_url TEXT,
  linkedin_url TEXT,
  whatsapp_link TEXT,
  stage TEXT DEFAULT 'new',
  score INT,
  tier TEXT,
  confidence NUMERIC(3,2),
  source TEXT DEFAULT 'gmaps',
  dedupe_key TEXT,
  notes TEXT,
  enrich_error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (workspace_id, dedupe_key)
);

CREATE TABLE IF NOT EXISTS lead_signals (
  id SERIAL PRIMARY KEY,
  lead_id INT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  channel TEXT NOT NULL,
  signal TEXT NOT NULL,
  value TEXT,
  verified BOOLEAN DEFAULT false,
  observed_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (lead_id, channel, signal)
);

CREATE TABLE IF NOT EXISTS lead_scores (
  id SERIAL PRIMARY KEY,
  lead_id INT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  rule TEXT NOT NULL,
  points INT NOT NULL,
  detail TEXT,
  scored_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outreach_steps (
  id SERIAL PRIMARY KEY,
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  lead_id INT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  step INT NOT NULL,
  channel TEXT DEFAULT 'email',
  status TEXT DEFAULT 'pending',
  subject TEXT,
  body TEXT,
  scheduled_for TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  error TEXT
);

CREATE TABLE IF NOT EXISTS suppression (
  workspace_id INT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  reason TEXT,
  added_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (workspace_id, email)
);

CREATE TABLE IF NOT EXISTS runs (
  id SERIAL PRIMARY KEY,
  workspace_id INT REFERENCES workspaces(id) ON DELETE CASCADE,
  job TEXT NOT NULL,
  campaign_id INT,
  status TEXT DEFAULT 'running',
  found INT DEFAULT 0,
  errors INT DEFAULT 0,
  log TEXT,
  started_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS leads_workspace_campaign_tier_stage_idx
  ON leads (workspace_id, campaign_id, tier, stage);
CREATE INDEX IF NOT EXISTS lead_signals_lead_id_idx ON lead_signals (lead_id);
CREATE INDEX IF NOT EXISTS lead_scores_lead_id_idx ON lead_scores (lead_id);
CREATE INDEX IF NOT EXISTS outreach_steps_ws_status_sched_idx
  ON outreach_steps (workspace_id, status, scheduled_for);
CREATE INDEX IF NOT EXISTS runs_workspace_started_idx ON runs (workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS campaign_niches_campaign_id_idx ON campaign_niches (campaign_id);
CREATE INDEX IF NOT EXISTS campaign_locations_campaign_id_idx ON campaign_locations (campaign_id);

INSERT INTO workspaces (id, name) VALUES (1, 'default')
ON CONFLICT (id) DO NOTHING;
SELECT setval('workspaces_id_seq', GREATEST((SELECT MAX(id) FROM workspaces), 1));

INSERT INTO scoring_profiles (workspace_id, name, weights)
SELECT 1, 'Default SPEC',
  '{
    "has_website": 8,
    "category_match": 8,
    "rating_ge_4": 6,
    "reviews_ge_20": 6,
    "inside_location": 6,
    "opportunity_gap": 6,
    "meta_ads": 15,
    "google_ads": 10,
    "has_pixel_or_tag": 5,
    "email_mx_valid": 12,
    "valid_phone": 8,
    "whatsapp_link": 5,
    "active_social": 5
  }'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM scoring_profiles WHERE workspace_id = 1 AND name = 'Default SPEC'
);

INSERT INTO offer_profiles (workspace_id, name, pitch, pain_points, gap_hook_rules, templates)
SELECT 1,
  'Website redesign + Meta ads',
  'We redesign local business websites and run Meta ads that convert.',
  ARRAY['outdated website', 'no booking', 'ads without tracking'],
  '[
    {"signal": "no_pixel", "sentence": "noticed you run no tracking on your site"},
    {"signal": "no_booking", "sentence": "noticed visitors cannot book online"},
    {"signal": "running_ads_no_form", "sentence": "noticed you run ads but have no contact form"},
    {"signal": "no_https", "sentence": "noticed your site is still on HTTP"}
  ]'::jsonb,
  '{
    "step1": {
      "subject": "Quick idea for {{name}} in {{city}}",
      "body": "Hi {{name}},\n\nI help {{category}} businesses in {{city}} get more booked customers.\n{{gap_hook}}\n\nWould a short redesign + Meta ads test be useful?\n\nBest,\n{{sender_name}}"
    },
    "step2": {
      "subject": "Case note for {{category}} in {{city}}",
      "body": "Hi {{name}},\n\nSharing a quick value note: local {{category}} sites that fix {{gap_hook}} usually see clearer lead flow.\n\nHappy to show a 15-min mockup.\n\nBest,\n{{sender_name}}"
    },
    "step3": {
      "subject": "Worth a quick look?",
      "body": "Hi {{name}},\n\nClosing the loop — if now is not the time, no worries. If it is, I can send a one-page plan for {{name}}.\n\nBest,\n{{sender_name}}"
    }
  }'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM offer_profiles WHERE workspace_id = 1 AND name = 'Website redesign + Meta ads'
);
