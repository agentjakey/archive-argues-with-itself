# Exhibit runbook

The one page for running the offline kiosk at the festival, followable alone under
pressure. Prepare once with the network on, prove it with the demo self-test, and run
it with the network off. Every command is from the repository root with the venv, the
`.env` (key and the `CIVIC_*` paths), and the two data files in place.

This runbook is the offline kiosk (one laptop, local data files). For the cloud deploy
that serves both scopes from Cloudflare R2 onto a `/data` volume, see
[`deploy.md`](deploy.md); this page covers the festival pilot exhibit.

## 1. Boot sequence

1. Start the API (serves the built web app and the read-only endpoints):

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn archive_debugger.api.app:app --host 127.0.0.1 --port 8000
   ```

   The web app is built once during prep (`cd web; npm ci; npm run build; cd ..`); the
   API serves it at `/`. Wait for the uvicorn "Application startup complete" line.

2. Open the kiosk in a full-screen browser. Edge or Chrome, one tab:

   ```
   --kiosk --incognito --disable-pinch --overscroll-history-navigation=0 "http://127.0.0.1:8000/?kiosk=1&idle=30"
   ```

   `kiosk=1` enlarges type, hides the filter controls, and runs the attract loop.
   `idle=30` opens the first story after about 30 seconds with no touch, then cycles the
   stories. Note: after a visitor interacts and the screen returns home, the dwell falls
   back to the 60 second default (the idle value is not carried across a return-home in
   this build); both timings are fine for the floor.

3. Turn the Wi-Fi off. The exhibit is designed to run with no network; step 2 of the
   self-test proves it.

## 2. Demo self-test (the pre-doors ship gate)

One command runs all three offline checks and prints a single GREEN or RED:

```powershell
.\.venv\Scripts\python.exe scripts\demo_selftest.py
```

It runs `preflight.py` (needs the API up), `scan_coverage.py`, and
`offline_walkthrough.py` in order.

- **GREEN** means: the two data files are present, `/health` is up, every seed and story
  question is in the answer cache, every page image those reference is a real JPEG in the
  pack, offline retrieval loads and every answered question clears the frozen gate, all
  compare pins expand, and the request path degrades cleanly with the model unreachable.
  Clear to open the doors.
- **RED on the page pack** (preflight and scan_coverage naming missing page images): the
  pack is not built. Build it (section 3), then re-run. This is the expected state on a
  fresh machine.
- **RED, not the page pack**: read the sub-check output. If preflight cannot reach
  `/health`, the API is not running (section 1, step 1). If a data file is missing, restore
  `civic.db` / `vectors.db` to the `CIVIC_*` paths. If `offline_walkthrough` is red, the
  request path itself regressed; do not open the doors, fall back to the clip (section 6).

Do not go on stage until the self-test prints `DEMO SELF-TEST: GREEN`.

## 3. Build the page pack (network on, once)

The pack is the local page-image cache; it is the only piece the self-test cannot
manufacture offline. With the network on:

```powershell
.\.venv\Scripts\python.exe scripts\warm_cache.py http://127.0.0.1:8000
.\.venv\Scripts\python.exe scripts\offline_pack.py --contact you@example.com
.\.venv\Scripts\python.exe scripts\scan_coverage.py
```

`warm_cache.py` asks every seed question through the real model once (it prints a cost
estimate and asks first; a cached question costs nothing; the four stories use seed
questions, so this covers them). `offline_pack.py` fetches the thumbnail and medium image
for every passage in every cached answer and every story pin into `data/cache/pages/`;
roughly 1,500 pages at a polite half second each, so expect 20 to 30 minutes, and
re-running fetches only what is missing. Re-run `scan_coverage.py` until it prints
`GREEN: every surfaceable citation resolves to a local scan.` Then turn the Wi-Fi off and
run the full self-test (section 2).

## 4. What a visitor sees offline

- **Golden and story questions are instant and cited.** Every example tile and every
  story is served from the answer cache, with numbered citations that open the scanned
  page from the local pack. None of them calls the model.
- **A novel typed question with the Wi-Fi off never errors.** The model is unreachable, so
  `/ask` returns the limited-mode "here is the record" state: the retrieved passages and
  their scans, with a plain note that the written answer is unavailable offline. It is a
  designed 200, not a raw error (N6).
- **The sensitivity layer** shows on harm-adjacent content, computed on serve over the
  evidence actually shown:
  - an entry advisory on first arrival;
  - a contextual note plus topic-appropriate crisis lines on any flagged result, across
    the answer, the compare view, and the limited-mode paths alike;
  - a tap-through interstitial before the two heaviest topics only (residential-school
    health and coerced sterilization), on by default. The scanned page is always shown;
    nothing is hidden or sanitized (N8).

## 5. Five failure drills and recovery

1. **App process crashes.** Relaunch the uvicorn line (section 1, step 1) and reopen the
   kiosk URL. For an unattended floor, the OS auto-restart set up during kiosk lockdown
   (a boot task plus a watchdog that relaunches uvicorn and the browser) does this for
   you; verify it during setup by killing the process and watching it return.
2. **Network drops mid-show.** Nothing to do. Cached questions and stories never call the
   model, page images come from the local pack, and a novel query degrades to limited
   mode. There is no hard fail; the show continues.
3. **Power loss.** The laptop should be set to power on after a cut (BIOS), auto-login,
   and launch the API and kiosk browser on boot (kiosk lockdown). After it comes back,
   run the self-test (section 2) before letting visitors touch it.
4. **Adversarial or garbage input.** Empty, huge, control-character, injection-style, and
   non-English inputs all resolve to a clean 200: either the frozen gate abstains or the
   path degrades to limited mode. The `offline_walkthrough` adversarial battery proves
   this. Recovery: none needed; touch the screen or wait for the attract loop to reset.
5. **Long run or memory drift.** The API holds about 0.7 GB and is stable, but reboot the
   laptop before doors each day and re-run the self-test, so every session starts clean.

## 6. Fallbacks

- **The looping demo clip.** A short recorded walk-through that plays on its own. Switch
  to it if the self-test cannot reach GREEN in time, or if the hardware fails in a way
  the drills above do not recover.
- **The printed handout.** The one-page explainer with the live URL and the QR code.
  Hand it out while you recover, or as the take-away in either case.

## 7. If X breaks, do Y

| Symptom | Do this |
| --- | --- |
| Self-test RED, names the page pack | Build the pack (section 3), re-run the self-test |
| preflight cannot reach `/health` | Start the API (section 1, step 1) |
| `civic.db` / `vectors.db` missing | Restore them to the `CIVIC_*` paths in `.env`, restart the API |
| Screen frozen or wrong view | Reload the kiosk URL (F5); all state is in the URL, so it is a clean start |
| App process gone | Relaunch uvicorn and the kiosk URL; confirm the watchdog relaunches it |
| Wi-Fi dropped | Nothing; the exhibit runs offline by design |
| A typed question shows limited mode | Expected offline; point the visitor at the example tiles and stories |
| Anything else, minutes to doors | Switch to the looping clip and the handout (section 6) |

## Reset between visitors and days

- During the attract loop, any touch returns to the home screen on its own.
- To reset by hand, reload the kiosk URL (F5): all state is in the URL, so a reload of the
  bare kiosk URL is a clean start.
- The answer cache and the page pack live in `data/cache/` and survive restarts; nothing
  needs clearing between visitors or between days.
