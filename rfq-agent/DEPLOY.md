# Railway Deployment

This repo deploys as **two Railway services** from one GitHub repository: a FastAPI backend and a Vite/React frontend. Each service sets its own Root Directory so Railway only builds what that service owns.

## 1. Prerequisites

- A Railway account connected to the GitHub repo.
- A Google Gemini API key (required). Get one at https://aistudio.google.com.
- An Anthropic API key (optional, for feasibility/report agents).

## 2. Create the backend service

1. In Railway: **New Project → Deploy from GitHub repo** → pick this repo.
2. In the service **Settings**, set **Root Directory** to `rfq-agent/backend`.
3. Railway reads [backend/railway.toml](backend/railway.toml):
   - Builder: Nixpacks (auto-detects Python + `requirements.txt`)
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Health check: `/api/health`
4. **Variables** — set these on the service:
   - `GEMINI_API_KEY` = your Gemini key
   - `ANTHROPIC_API_KEY` = your Anthropic key (optional)
   - `ALLOWED_ORIGINS` = the full frontend URL you'll use, e.g. `https://rfq-frontend-production.up.railway.app`
     - Any `*.up.railway.app` origin is already allowed by regex in [main.py](backend/main.py), so this is mainly for custom domains.
     - Use `*` to allow all origins (disables credentials).
   - `DATABASE_URL` (optional) — if you attach Railway Postgres, set this to `${{Postgres.DATABASE_URL}}`. Otherwise the app uses SQLite at `./rfq_agent.db`.
5. **Volume** (recommended) — attach a Railway Volume to persist uploads and the SQLite DB across redeploys:
   - Mount path: `/app/uploads`
   - Size: 2–5 GB is plenty to start.
   - Without a volume, every redeploy wipes uploaded PDFs, generated images, and the SQLite DB.
6. Deploy. Railway exposes a public URL — copy it (you need it for the frontend's `VITE_BACKEND_URL`).

## 3. Create the frontend service

1. In the same Railway project: **+ New → GitHub Repo** (same repo).
2. **Root Directory** = `rfq-agent/frontend`.
3. Railway reads [frontend/railway.toml](frontend/railway.toml):
   - Build: `npm ci && npm run build` (Nixpacks default for Vite)
   - Start: `npm start` → `serve -s dist` on `$PORT` (production static host with SPA fallback)
4. **Variables**:
   - `VITE_BACKEND_URL` = the backend's public URL (no trailing slash, no `/api` suffix), e.g. `https://rfq-backend-production.up.railway.app`
   - `VITE_BALLOON_EDITOR_URL` (optional) — if you deploy the balloon-editor as a third service. Leave unset to hide the "Open Editor" button.
5. Deploy. Railway gives you the frontend public URL.
6. Go back to the backend service's `ALLOWED_ORIGINS` and paste in the frontend URL if not already covered by the `*.up.railway.app` regex.

## 4. Verify

- **Backend health**: `curl https://<backend>.up.railway.app/api/health` → `{"status":"ok"}`.
- **Frontend**: open the frontend URL. The dashboard should load RFQ data; image previews pull from the backend's `/uploads/*`.
- **Uploading a drawing** (Dashboard → New RFQ) should:
  - Save the PDF to the volume
  - Trigger the analyze pipeline
  - Populate the BALLOONING_REVIEW screen with the rendered image

## 5. Updating after code changes

Push to `main` → Railway auto-redeploys both services. The backend's volume preserves uploads and the SQLite DB across redeploys. The frontend rebuilds `dist/` from source on every deploy.

## 6. Optional: Postgres instead of SQLite

1. In the Railway project: **+ New → Database → Add PostgreSQL**.
2. On the backend service, set `DATABASE_URL=${{Postgres.DATABASE_URL}}`.
3. Add `psycopg2-binary` to [requirements.txt](backend/requirements.txt) if not already present.
4. Redeploy. `database.py` already rewrites the `postgres://` scheme to `postgresql://` for SQLAlchemy.

## 7. Optional: balloon editor as a third service

The [frontend/balloon-editor/](frontend/balloon-editor) sub-app is a separate Vite project. To deploy it:

1. New Railway service, Root Directory = `rfq-agent/frontend/balloon-editor`.
2. It expects to be opened with `?rfq_id=...&api=<backend-url>` query params.
3. Set `VITE_BALLOON_EDITOR_URL` on the main frontend to this service's URL to expose the "Open Editor" button.

## 8. Environment variable reference

| Variable | Service | Required | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | backend | yes | Gemini vision + ballooning |
| `ANTHROPIC_API_KEY` | backend | no | Claude-powered feasibility/report agents |
| `ALLOWED_ORIGINS` | backend | recommended | Comma-separated frontend origins for CORS |
| `DATABASE_URL` | backend | no | Postgres URL; falls back to SQLite |
| `PORT` | backend & frontend | auto | Injected by Railway; code already respects it |
| `VITE_BACKEND_URL` | frontend | yes | Backend public URL (no `/api` suffix) |
| `VITE_BALLOON_EDITOR_URL` | frontend | no | Hides button if unset |

## 9. Troubleshooting

- **CORS errors in browser console** — the frontend's exact origin isn't allowed. Add it to `ALLOWED_ORIGINS` on the backend and redeploy.
- **Images/PDFs 404 after redeploy** — you didn't attach a volume; Railway's filesystem is ephemeral. See step 2.5.
- **`VITE_BACKEND_URL` changes at build time only** — Vite inlines env vars during `npm run build`, so changing it in Railway requires a redeploy of the frontend (Railway does this automatically when you change a variable).
- **Backend cold-starts slow** — first request after a sleep triggers Nixpacks image warmup; subsequent requests are fast.
