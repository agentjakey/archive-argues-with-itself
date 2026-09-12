# Exhibit runbook

The one page for running the offline kiosk. Prep once with the network on; on the
day, prove it with `preflight.py` and run it with the network off.

## One-time prep (network on)

From the repository root, with the venv, `.env` (key and the `CIVIC_*` paths), and
the data files in place (see the README "Run it yourself").

1. Build the web app and start the API:

   ```powershell
   cd web; npm ci; npm run build; cd ..
   .\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
   ```

2. In a second terminal, warm the answer cache. This asks every seed question through
   the real model once (it prints a cost estimate and asks before sending; it is safe
   to re-run, since a cached question costs nothing). The four stories use seed
   questions, so this covers them too.

   ```powershell
   .\.venv\Scripts\python.exe scripts\warm_cache.py http://127.0.0.1:8000
   ```

3. Build the offline pack: the page thumbnail and medium image for every passage in
   every cached answer and every story pin, fetched once from archive.org into
   `data/cache/pages/`.

   ```powershell
   .\.venv\Scripts\python.exe scripts\offline_pack.py --contact you@example.com
   ```

   Re-running fetches only what is missing. If it reports a story question that is not
   in the cache, run step 2 again.

## Day-of check (network off)

Turn the Wi-Fi off. Start the API (step 1's uvicorn line), then in a second terminal:

```powershell
.\.venv\Scripts\python.exe scripts\preflight.py
```

It prints a green or red line for each check: `/health` responds, the answer cache
has an entry for every seed question and every story, and every page image those
reference is present in `data/cache/pages/`. It exits non-zero and lists the missing
ids if anything is red. Do not go on stage until it prints "GREEN: every check
passed."

Then open the kiosk in a full-screen browser (F11):

```
http://127.0.0.1:8000/?kiosk=1&offline=1
```

`offline=1` hides the ask box, so visitors open only the example questions and the
stories, none of which call the model. See `docs/demo.md` for the browser flags and
the attract loop.

## If the Wi-Fi dies mid-show

Nothing to do. Cached questions and stories never call the model, and the page images
come from the local pack. The only call the app can make is the model, and that only
happens for a question that is not cached, which the offline kiosk URL does not allow.

## Reset between visitors

- During the attract loop, any touch returns to the home screen on its own.
- To reset by hand, reload the kiosk URL (F5); all state is in the URL, so a reload of
  the bare kiosk URL is a clean start.
- The answer cache and the offline pack live in `data/cache/` and survive restarts;
  nothing needs clearing between visitors or between days.
