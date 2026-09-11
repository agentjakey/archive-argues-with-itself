# Deploying

Two pieces: the read-only API (FastAPI, Docker, Fly.io, with the two data files
on a volume) and the web app (Vite, Vercel, pointed at the API). The API also
serves `web/dist` itself, so Vercel is optional; the single-process laptop
fallback at the end needs neither.

Nothing here is automatic. Every command is run by hand; nothing in CI deploys.

## Paths and environment

The config paths in `config/pilot.toml` are overridable by environment
variables, so the same image runs against a mounted volume:

| variable | overrides | container default |
| --- | --- | --- |
| `CIVIC_DB_PATH` | `[index].db_path` | `/data/civic.db` |
| `CIVIC_INDEX_PATH` | `[retrieve].index_path` | `/data/index/vectors.db` |
| `CIVIC_CACHE_PATH` | answer cache file | `/data/cache/answers.db` |
| `PORT` | uvicorn port | `8080` |
| `ALLOWED_ORIGINS` | CORS allow-list (comma-separated); unset = same-origin only | (secret) |
| `ANTHROPIC_API_KEY` | the only external call the server makes | (secret) |

The Dockerfile bakes the query embedding model into the image at build time, so
the running container makes no download; its only network call is the LLM API.

## 1. Fly.io (API)

Prerequisites: `flyctl` installed and logged in (`fly auth login`); the web app
built locally so `web/dist` exists (`cd web && npm ci && npm run build`); the
two data files present locally (`civic.db` ~1.9 GB, `index/vectors.db` ~1.5 GB).

```powershell
# from the repo root

# 1. Create the app from fly.toml without deploying. Accept the existing config.
fly launch --no-deploy --copy-config --name archive-argues-with-itself --region sea

# 2. Create the 10 GB volume the config mounts at /data.
fly volumes create civic_data --region sea --size 10 --app archive-argues-with-itself

# 3. Secrets. ALLOWED_ORIGINS is the Vercel origin(s); omit it if the API serves
#    the web app itself (same origin).
fly secrets set --app archive-argues-with-itself `
  ANTHROPIC_API_KEY=<your key> `
  ALLOWED_ORIGINS=https://<vercel-app>.vercel.app

# 4. First deploy. The container starts, finds no data files, and waits (the
#    entrypoint polls every 30 s); the health check stays red until step 5.
fly deploy --app archive-argues-with-itself

# 5. Upload the data files onto the volume (sftp goes through the running
#    machine; 3.4 GB takes a while on a home uplink).
fly sftp shell --app archive-argues-with-itself
#   at the ">>" prompt:
#   mkdir /data/index
#   put civic.db /data/civic.db
#   put index/vectors.db /data/index/vectors.db
#   exit

# 6. The waiting entrypoint picks the files up on its next poll and starts
#    uvicorn. Confirm:
fly logs --app archive-argues-with-itself
curl https://archive-argues-with-itself.fly.dev/health
```

Redeploys (`fly deploy`) keep the volume; the data files are uploaded once.
Rebuilding the corpus locally means re-running step 5 and deleting
`/data/cache/answers.db` on the volume (`fly ssh console` then `rm`), because
cached answers were generated against the old index.

Sizing: `[[vm]] memory = "4gb"` in `fly.toml` is the working assumption for a
flat cosine scan over 745,893 vectors plus the sqlite page cache; watch
`fly status` and query latency before dropping it. `auto_stop_machines` is off
so the page cache is not lost between visitors.

## 2. Vercel (web app)

The web app is a static Vite build under `web/`. `web/vercel.json` sets the
framework, install/build commands, output directory, and the SPA rewrite. The
one variable is `VITE_API_BASE`, the API origin without a trailing slash; it is
compiled into the bundle at build time.

Dashboard route: New Project, import the GitHub repo, set **Root Directory** to
`web`, add environment variable `VITE_API_BASE = https://archive-argues-with-itself.fly.dev`
for Production (and Preview if wanted), Deploy.

CLI route:

```powershell
cd web
vercel link                                           # choose or create the project; root is this directory
vercel env add VITE_API_BASE production               # paste: https://archive-argues-with-itself.fly.dev
vercel --prod
```

Then put the resulting origin into the API's `ALLOWED_ORIGINS` secret (step 3
above; comma-separate several origins, for example a preview URL). Without it
the browser blocks the cross-origin `/ask` call.

## 3. Laptop fallback (single process, no cloud)

The API serves `web/dist` at `/`, so one process is the whole demo:

```powershell
cd web; npm ci; npm run build; cd ..
.\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 0.0.0.0 --port 8000
```

Open `http://<laptop-ip>:8000/` from any device on the same network (append
`?kiosk=1` for the exhibit mode). `ANTHROPIC_API_KEY` comes from `.env` in the
repo root; `ALLOWED_ORIGINS` is not needed because everything is same-origin.
The same container runs locally too:

```powershell
docker build -t archive-argues .
docker run --rm -p 8080:8080 --env-file .env `
  -v "${PWD}\civic.db:/data/civic.db:ro" `
  -v "${PWD}\index\vectors.db:/data/index/vectors.db:ro" `
  archive-argues
```
