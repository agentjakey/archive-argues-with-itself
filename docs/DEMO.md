# Running the exhibit

One laptop, one process, no internet required once prepared. The app shows real
scanned pages from the offline pack, answers every seed question from its cache,
and cycles through the stories when nobody is touching it.

Each story pairs two pages from the record, years apart, on one question; the
attract loop opens them in turn.

![The Stories index: four curated question cards, each pairing two pages years apart](images/stories.png)

## Prepare (with internet, once)

From the repository root, with the venv, `.env` (key and `CIVIC_*` paths) and
the data files in place (README "Run it yourself").

1. Build the web app and start the API:

   ```powershell
   cd web; npm ci; npm run build; cd ..
   .\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
   ```

2. In a second terminal, warm the answer cache (every seed question through the
   real model; prints a cost estimate and asks first; safe to re-run):

   ```powershell
   .\.venv\Scripts\python.exe scripts\warm_cache.py http://127.0.0.1:8000
   ```

   The four stories in `config/stories.json` use seed questions, so this also
   caches them. The script's last line counts cached / answered / abstained /
   failed; failed must be 0.

3. Build the offline pack of page images (thumbnail and medium image for every
   passage in every cached answer and every story pin; fetched once from
   archive.org into `data/cache/pages/`):

   ```powershell
   .\.venv\Scripts\python.exe scripts\offline_pack.py --dry-run          # counts, and any story not yet cached
   .\.venv\Scripts\python.exe scripts\offline_pack.py --contact you@example.com
   ```

   Roughly 1,500 pages for 50 cached answers (two images each) at a polite half
   second per request: expect 20-30 minutes. Re-running fetches only what is
   missing. If it reports story questions not in the cache, run step 2 again.

4. Check without the network: disconnect Wi-Fi, reload the app, open a story and
   an example question. Pages should render from `/pages/...` (the evidence rows
   carry `offline: true`), and the answer should say "served from cache".

## Run (at the venue)

```powershell
.\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
```

Open the kiosk URL in a full-screen browser (F11):

```
http://127.0.0.1:8000/?kiosk=1
```

Kiosk mode enlarges type, hides the filter controls, and runs the attract loop:
after 60 seconds without a touch, the app opens a story (question, answer, two
pages side by side) and moves to the next every 20 seconds; any touch or key
returns to the home screen.

Recommended browser flags for an unattended kiosk (Edge or Chrome):
`--kiosk --incognito --disable-pinch --overscroll-history-navigation=0 "http://127.0.0.1:8000/?kiosk=1"`.

## If the Wi-Fi dies

Nothing. Cached questions and stories never call the model; page images come
from the offline pack; the only network call the app can make is the model, and
that happens only for a question that is not cached. If a visitor types a new
question with no network, the app shows the server's error in plain words; the
example chips and stories keep working.

To keep the exhibit fully offline-safe, add `offline=1` to the kiosk URL:

```
http://127.0.0.1:8000/?kiosk=1&offline=1
```

`offline=1` hides the ask box, so visitors can only open the example questions
(all cached) and the stories; nothing on screen can trigger a model call. The
flag is preserved as the visitor moves around and by the attract loop's return
home. Without it, kiosk mode hides the filter controls but leaves the question
box available, and a typed question needs the network.

## Reset between visitors

- Touch or press any key during the attract loop: the app returns to the home
  screen on its own.
- To reset by hand: reload `http://127.0.0.1:8000/?kiosk=1` (F5). All state is
  in the URL, so a reload of the bare kiosk URL is a clean start.
- The answer cache and the offline pack live in `data/cache/` and survive
  restarts; nothing needs clearing between visitors or days.

## What the laptop needs

The API process holds about 0.7 GB; keep the two data files on a local disk
(not a synced folder) and the laptop plugged in with sleep disabled. A stub
`/ask` takes 1-2 seconds on a laptop with the data files cached; the first query
after a cold start is slower while the files load.
