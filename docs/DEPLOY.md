# Deploying

The API runs from one Docker image on any host with a persistent disk. On boot the
container provisions each ENABLED scope's two data files onto the disk from that
scope's configured source -- Cloudflare R2 by default, or a GitHub release as a
fallback -- verifies their sha256 against `config/scopes.toml`, and serves; a file
already present with the right hash is not re-downloaded, so later boots start in
seconds. The web app is built inside the image and served at `/`.

Two scopes ship this way: the frozen public_health pilot and the national microlog
corpus. Both are sourced from R2, and the UI lands on microlog with the pilot in the
switcher. The pilot's bytes and answers are unchanged (same `civic.db`); only its
delivery origin moves to R2, and the GitHub-release path stays available as a
fallback (see "Both scopes from R2" below).

The steps below use Railway. Nothing deploys automatically from CI.

## What you need

- A GitHub account with this repository (fork or clone), `gh` installed and
  logged in (`gh auth login`), for the one-time data release.
- A Railway account connected to GitHub.
- Your API key for the configured language-model provider (the variable named in `.env.example`).
- A Cloudflare R2 bucket (S3-compatible) with its endpoint, access key id, and secret,
  for hosting the scope data (see "Both scopes from R2").
- The scope data files on your machine (both scopes' db + index), built by the
  Reproduce steps in the README, to upload to R2 once.

## Environment variables

| variable | value on Railway | meaning |
| --- | --- | --- |
| `CIVIC_DB_PATH` | `/data/civic.db` | pilot corpus database (image default; under the `/data` volume) |
| `CIVIC_INDEX_PATH` | `/data/index/vectors.db` | pilot dense index (under the `/data` volume) |
| `CIVIC_CACHE_PATH` | `/data/cache/answers.db` | pilot answer cache (under the `/data` volume) |
| `MICROLOG_DB_PATH` | `/data/microlog/civic_microlog.db` | microlog corpus database (image default; relocates the fenced scope onto the `/data` volume) |
| `MICROLOG_INDEX_PATH` | `/data/microlog/index/vectors_microlog.db` | microlog dense index (its answer cache follows at `/data/microlog/cache/answers.db`) |
| `R2_ENDPOINT` | `https://<accountid>.r2.cloudflarestorage.com` | Cloudflare R2 S3 endpoint (the scope data source) |
| `R2_BUCKET` | your bucket | R2 bucket holding the `pilot/*` and `microlog/*` objects |
| `R2_ACCESS_KEY_ID` | your R2 key id | R2 access key id |
| `R2_SECRET_ACCESS_KEY` | your R2 secret | R2 secret (set it as a Railway *secret* variable) |
| `CIVIC_ENABLED_SCOPES` | `pilot,microlog` | scopes to provision and serve (both here); unset serves the pilot only |
| `CIVIC_DEFAULT_SCOPE` | `microlog` | scope the UI lands on first (default microlog; both stay in the switcher) |
| `DATA_RELEASE_URL` | `https://github.com/<you>/archive-argues-with-itself/releases/download/data-v1` | fallback only: the pilot's GitHub release, used when the R2 vars are absent (its files are under GitHub's 2 GiB cap). microlog has no release fallback. |
| `ANTHROPIC_API_KEY` | your key | the only external call the server makes at serve time |
| `ALLOWED_ORIGINS` | (unset) | only for a separately hosted web app; comma-separated origins |
| `PORT` | set by Railway | uvicorn listens on it |

## Both scopes from R2 (pilot + microlog)

The two data files per scope live in one R2 bucket, keyed by scope:

```
pilot/civic.db               pilot/vectors.db
microlog/civic_microlog.db   microlog/vectors_microlog.db
```

They are uploaded once with `scripts/upload_scopes_to_r2.py` (it prints and records
their sha256; those hashes are already filled into `config/scopes.toml`, which the
boot verifies against). To serve both scopes:

1. **Upload the four files to R2** (from your machine, one time):

   ```powershell
   $env:R2_ENDPOINT = "https://<accountid>.r2.cloudflarestorage.com"
   $env:R2_BUCKET = "<bucket>"
   $env:R2_ACCESS_KEY_ID = "<key id>"
   .\.venv\Scripts\python.exe scripts\upload_scopes_to_r2.py    # prompts for the secret, no echo
   ```

2. **Mount the volume at `/data`** (Railway: Settings -> Volumes -> Add Volume,
   mount path `/data`). These path values are the image defaults and all sit under that
   mount; set them explicitly to be sure (copy-paste):

   ```
   CIVIC_DB_PATH=/data/civic.db
   CIVIC_INDEX_PATH=/data/index/vectors.db
   CIVIC_CACHE_PATH=/data/cache/answers.db
   MICROLOG_DB_PATH=/data/microlog/civic_microlog.db
   MICROLOG_INDEX_PATH=/data/microlog/index/vectors_microlog.db
   ```

   The pilot honors the `CIVIC_*` paths; the microlog scope is fenced and ignores
   `CIVIC_*`, so it is relocated onto the volume with its own `MICROLOG_DB_PATH` /
   `MICROLOG_INDEX_PATH` (its answer cache follows beside the db, at
   `/data/microlog/cache/answers.db`). With these set, every db, index, and cache for
   both scopes sits under the single `/data` mount; nothing writes outside it, and
   nothing is re-downloaded on restart.

3. **Set the R2 and scope variables**: `R2_ENDPOINT`, `R2_BUCKET`,
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (a secret variable),
   `CIVIC_ENABLED_SCOPES=pilot,microlog`, `CIVIC_DEFAULT_SCOPE=microlog`, and
   `ANTHROPIC_API_KEY`. Size the volume for both scopes: about 10.5 GiB of data, so
   ~15 GB gives headroom for the answer cache and a partial download.

4. **Deploy.** The boot log lists each file verified or downloaded, then
   `Application startup complete`; `/scopes` reports `"default": "microlog"` with
   both scopes listed. Preview the plan without a container with
   `python -m archive_debugger.boot --dry-run` (no network, no download).

If the R2 vars are absent, the pilot falls back to its GitHub release
(`DATA_RELEASE_URL`) and boots exactly as before. microlog (files over GitHub's
2 GiB per-asset cap) is R2-only: with R2 unavailable and no local copy present, its
boot fails fast with a message naming the scope and key, and the server does not
start half-served.

### Cost: stop the service when idle

The corpus is large and the exhibit is not in use continuously, so the service is
stopped when idle to control cost and started again when needed (Railway: stop the
service, or scale it to zero, from the service menu). Because the data is cached on
the `/data` volume and verified by hash, a restart re-attaches the volume and
serves in seconds without re-downloading; only a first boot onto a cold volume pays
the one-time R2 download.

## Steps (pilot only, GitHub release)

The steps below deploy the pilot alone from a GitHub release (no R2). For the
two-scope R2 deploy, use the section above.

1. **Push** the repository to GitHub (your fork or your own repo).

2. **Publish the data release** (one time, from the repo root, with the data files
   at the paths in your `.env`):

   ```powershell
   .\.venv\Scripts\python.exe scripts\make_data_release.py
   ```

   It writes `data-release.sha256` and prints the exact `gh release create data-v1 ...`
   command with both files and the checksum file as assets. Run that command. The
   upload is bound by your uplink (3.2 GiB; at 25 Mbps about 18 minutes). Each asset
   is under GitHub's 2 GiB per-file limit; the script refuses larger files.

3. **Railway: New Project -> Deploy from GitHub repo**, pick the repository.
   Railway reads `railway.json` (Dockerfile build, health check on `/health`,
   one replica, restart on failure). The first build takes several minutes:
   node stage, python stage, and the embedding model baked into the image.

4. **Add a volume**: in the service, Settings -> Volumes -> Add Volume, mount
   path `/data`, size 10 GB (data 3.2 GiB, cache, and headroom for a resumed
   download's partial file).

5. **Set variables** (service -> Variables): `CIVIC_DB_PATH`, `CIVIC_INDEX_PATH`,
   `DATA_RELEASE_URL` (with your GitHub user and the tag from step 2), and
   `ANTHROPIC_API_KEY`, with the values from the table above.

6. **Deploy** (Railway redeploys when variables change; otherwise Deploy from
   the service menu).

7. **Watch the logs**. You will see `civic.db: downloading from ...`, a line every
   100 MB with the rate, `checksum ok` for each file, then
   `Application startup complete`. The health check waits up to 30 minutes for
   this first boot (`healthcheckTimeout` in `railway.json`); GitHub releases
   usually download at tens of MB/s, so expect a few minutes. If the download is
   interrupted the container restarts and resumes from the partial file.

8. **Open the public domain**: Settings -> Networking -> Generate Domain. Open it;
   the reading-room UI loads, `/health` shows `items: 3477`.

9. **Smoke test** from your machine (no key needed, no model called):

   ```powershell
   .\.venv\Scripts\python.exe scripts\smoke.py https://<your-service>.up.railway.app
   ```

10. **Warm the answer cache** (real provider; prints a cost estimate and asks
    before sending; safe to re-run, cached questions are free):

    ```powershell
    .\.venv\Scripts\python.exe scripts\warm_cache.py https://<your-service>.up.railway.app
    ```

Later deploys keep the volume; the files are verified, not re-downloaded. A new
corpus is a new release tag (`data-v2`) and a changed `DATA_RELEASE_URL`: the
container sees the checksum mismatch, re-downloads, and the answer cache
invalidates itself because its key includes the data files' size and mtime.

## Sizing (measured)

- Disk: data 3.2 GiB (civic.db 1,878,642,688 bytes, vectors.db 1,557,426,176
  bytes) plus the answer cache; a resumed download needs no extra space beyond
  the partial file itself. 10 GB is comfortable; 5 GB works.
- Memory: inside this image on a Linux volume, after `/health`, `/examples`,
  `/ask`, `/coverage`: RSS high-water mark 737 MB, container 681 MiB. 2 GB runs
  it; 4 GB also keeps both data files in page cache, which is what makes the
  dense flat scan take about two seconds instead of a disk read per query
  (stub `/ask` 1.6 s, `/coverage` 2.2 s measured with the files cached). On
  Railway, memory is allocated on demand up to the plan limit; if `/ask` is slow,
  the plan's memory ceiling is the first thing to check.

## Fly, Hugging Face Space, or any Docker host

The same image and the same environment variables work anywhere with a
persistent disk mounted at the `CIVIC_*` paths: build the `Dockerfile`, mount a
disk at `/data`, set `DATA_RELEASE_URL` and `ANTHROPIC_API_KEY`, expose `$PORT`
(default 8080), and point the host's health check at `/health` with a start
period long enough for the first download. Without `DATA_RELEASE_URL` the
container waits for the files to appear under `/data` (for hosts where you copy
them in by hand) and starts as soon as they do, without checksum verification.

## Local check with Docker

```powershell
docker build -t archive-argues .
docker volume create civic_data_local
docker run -d --name archive-argues -p 8080:8080 --memory 4g --env-file .env `
  -e DATA_RELEASE_URL=https://github.com/<you>/archive-argues-with-itself/releases/download/data-v1 `
  -v civic_data_local:/data archive-argues
docker logs -f archive-argues                    # download progress, then "Application startup complete"
.\.venv\Scripts\python.exe scripts\smoke.py http://127.0.0.1:8080
docker rm -f archive-argues                      # the volume keeps the files
```

(Use a named volume, not a Windows bind mount of the data files: Docker
Desktop's file share cannot stream the 1.45 GiB flat scan and `/ask` times out.)

## Troubleshooting

- Log says `missing [...] and DATA_RELEASE_URL is not set`: set the variable
  (step 5); the container retries every 30 s.
- `download error: HTTP Error 404`: the tag or asset name in `DATA_RELEASE_URL`
  is wrong; it must end in `/releases/download/<tag>` and the release must hold
  `civic.db`, `vectors.db`, `data-release.sha256`.
- `downloaded file does not match data-release.sha256`: the release assets and
  the checksum file are from different builds; re-run `make_data_release.py`
  and upload all three together.
- `/ask` returns `{"error": "ANTHROPIC_API_KEY is not set on the server"}`: set
  the variable; Railway redeploys.
- Health check fails after the download finished: check the service is on the
  port Railway injects as `PORT` (the entrypoint uses it) and that the volume is
  mounted at `/data`.
