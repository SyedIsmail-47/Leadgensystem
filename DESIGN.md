# DESIGN.md: Leadgensystem Dashboard

Streamlit multipage app. Dense operator dashboard. Shared components in `dashboard/ui.py`.

## Visual tokens
Set in `.streamlit/config.toml` and injected CSS.
| Token | Light | Dark |
|---|---|---|
| Background | `#F7F8FA` | `#0F1115` |
| Surface | `#FFFFFF` | `#171A21` |
| Border | `#E3E6EB` | `#2A2F3A` |
| Text | `#14171F` | `#E8EAF0` |
| Muted | `#667085` | `#9AA3B2` |
| Primary | `#2563EB` | `#4C8DFF` |
| Tier A | `#16A34A` | `#34D399` |
| Tier B | `#D97706` | `#FBBF24` |
| Tier C | `#94A3B8` | `#64748B` |
| Danger | `#DC2626` | `#F87171` |

Font: Inter (fallback system-ui). Radius 10px cards, 6px chips.

## Navigation
Overview · Leads · Lead Detail · Campaigns · Campaign Builder · Outreach · Runs & Logs · Settings

## Pages
- **Overview**: KPIs, funnel, charts, needs-attention
- **Leads**: filters, table, bulk actions, CSV export
- **Lead Detail**: contact, score breakdown, signals, notes
- **Campaigns**: list with Run now / Pause / Delete
- **Campaign Builder**: wizard Targets → Filters → Sources → Scoring → Offer & Sender → Schedule & Review
- **Outreach**: pending / scheduled / sent / suppressed; templates from offer profile
- **Runs & Logs**: runs table, blocked banner
- **Settings**: Offer Profiles, Sender Profiles (SMTP test), Scoring Profiles, Account

## UX
Destructive actions need confirm checkbox. Spinners/toasts. Empty states with next action. `layout="wide"`.
