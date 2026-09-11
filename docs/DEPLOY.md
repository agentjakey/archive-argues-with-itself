# Deploying

The API runs from one Docker image on any host with a persistent disk. On first
boot the container downloads the two data files (about 3.2 GiB) from a GitHub
release, verifies their checksums, and serves; on every later boot it verifies
the files already on the disk and starts in seconds. The web app is built inside
the image and served at `/`.

The steps below use Railway. Nothing deploys automatically from CI.

## What you need

- A GitHub account with this repository (fork or clone), `gh` installed and
  logged in (`gh auth login`), for the one-time data release.
- A Railway account connected to GitHub.
- Your Anthropic API key.
- The two data files on your machine, built by the Reproduce steps in the README
  (or downloaded from an existing release, see the README "Run it yourself").

## Environment variables

| variable | value on Railway | meaning |
| --- | --- | --- |
| `CIVIC_DB_PATH` | `/data/civic.db` | corpus database on the volume |
| `CIVIC_INDEX_PATH` | `/data/index/vectors.db` | dense index on the volume |
| `CIVIC_CACHE_PATH` | `/data/cache/answers.db` | answer cache (image default; set it only to move it) |
| `DATA_RELEASE_URL` | `https://github.com/<you>/archive-argues-with-itself/releases/download/data-v1` | base URL of the release assets; the container downloads `civic.db`, `vectors.db`, `data-release.sha256` from it |
| `ANTHROPIC_API_KEY` | your key | the only external call the server makes |
| `ALLOWED_ORIGINS` | (unset) | only for a separately hosted web app; comma-separated origins |
| `PORT` | set by Railway | uvicorn listens on it |

## Steps

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
