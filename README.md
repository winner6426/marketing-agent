# Marketing Agent

A multi-agent pipeline that turns a campaign brief into validated, multi-channel marketing content for an electric-vehicle dealership. A person must approve everything before it is published.

Language models write the copy, but they never write figures directly. They emit placeholders that code resolves from the database, so every price or specification traces back to a source.

## Pipeline

```
brief_analyst (<-> clarification) -> planner -> writer -> channel_validation -> brand_validation -> fact_check
    -> retry_counter (-> writer) -> scheduler -> quality_judge -> approval -> finalize_approval
```

`clarification` and `approval` pause the graph until a person responds. The three validation tiers run without calling a model and can block content. `quality_judge` only gives advisory scores.

Generated ads are written in Vietnamese. The code, prompts and API are in English. The Vietnamese vocabulary that guards must match lives only in `backend/src/content_locale.py`.

## Layout

```
backend/
  src/
    main.py, config.py
    utils.py            Normalization, Vietnam time, reference cache, rate limiter
    content_locale.py   Vietnamese vocabulary used in generated ads
    api/                auth, admin, manager, marketer routers; common.py holds role checks and errors
    services/           auth_service, admin_service, manager_service, marketer_service; shared.py
    agents/             campaign_graph, campaign_runner, guardrails, llm, rag
      nodes/            One file per pipeline step
    models/             db.py (tables), campaign_state.py, catalog.py
  scripts/              Operational commands
  tests/
```

Dependencies point one way: `api -> services -> agents -> models`.

## Setup

Requires Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # on macOS/Linux: .venv/bin/python
cp .env.example .env                                      # then fill in the values
.venv/Scripts/python -m uvicorn src.main:app --reload --env-file .env
```

The API docs are served at `http://localhost:8000/docs`.

Tables are created on first use. An account can only become an admin from the command line:

```bash
.venv/Scripts/python -m scripts.promote_admin admin@example.com
```

## Authentication

`POST /api/auth/register` and `POST /api/auth/login` proxy Supabase Auth, which stores the credentials. Access tokens are verified locally. Roles always come from `user_profiles`, never from the token, and every new account starts as a `marketer`.

## API

| Prefix | Role | Purpose |
|---|---|---|
| `/api/auth` | Public or any user | Register, log in, refresh, log out, profile |
| `/api/marketer` | `marketer` | Campaigns, chat sessions and drafts, content editing, manual sends |
| `/api/manager` | `manager` | Review queue, approve or reject, publish, analytics, audit log |
| `/api/admin` | `admin` | User roles, all campaigns, publishing channels |

Operations that spend LLM quota or publish content require an `Idempotency-Key` header. Every error has the shape `{"error": {"code", "message", "details"}}`.

## Reference data

The pipeline stops with a clear error until these tables are seeded: `products`, `product_variants`, `channel_specs`, `brand_rules`, `angles`, `cta_map` and `objections`.

Validators recognize these `channel_specs.rule_key` values: `hook_max_chars`, `body_max_chars`, `caption_max_chars`, `scene_max_chars`, `hashtag_count`, `primary_cta_max`, `emoji_max`, `emoji`, `sms_ucs2_3_segment` and `sms_gsm7_3_segment`. The writer also needs `sms_content_budget` for the `direct_message` channel. Other keys are reported as unchecked. A rule's `message` may use the `{excess}`, `{missing}` and `{actual}` fields.

Placeholders look like `{{price_vnd:VF3:eco:battery_included}}` and `{{range_km:VF3:standard}}`. Each one must name a variant (`eco`, `plus` or `standard`), and a price must also name a type.

## Frontend

`frontend/` is a React + Vite + Tailwind CSS app migrated from the earlier P-201 project. Components are styled with Tailwind classes in their JSX; `src/styles.css` is the only stylesheet and holds the Tailwind setup, theme tokens, the `dark` and `mobile` variants and keyframes. So far it has login, register, the marketer dashboard, the AI content chat, the campaign list and a campaign page where marketers read, edit (by hand or with AI), reschedule and submit content for review. Calendar, channels, sources, performance, manager and admin pages are not migrated yet; managers and admins see a notice after logging in.

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to the backend on port 8000
npm test
npm run build
```

The browser only talks to this backend: login and registration go through `/api/auth`, so the frontend needs no Supabase keys. For a deployed build, set `VITE_API_URL` to the backend origin and add the frontend origin to the backend's `CORS_ORIGINS`.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check .
```

Tests use a temporary SQLite database and a fake LLM, so they need no network access or API keys.
