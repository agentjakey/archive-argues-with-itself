# Running the exhibit on a kiosk

The exhibit is a static page: four games built from real pages that have been checked, with no
model and no engine behind them. Online it lives at archiveargues.org/exhibit. On a kiosk, a small
local server (`exhibit/kiosk/serve.py`, Python standard library only) serves the same release from
the kiosk's own disk, so it runs all day with no network. Page images come from archive.org's image
service when the kiosk is online. Offline, each page shows its own text and a note that the image
needs a connection. Page images are not stored on the kiosk. Caching them waits for permission
from Internet Archive Canada, and `config/exhibit.toml [images] offline_cache` stays false until then.

## Install

1. **Install Python 3.11 or newer**, for example into `C:\Exhibit\python`. Copy `exhibit\kiosk\serve.py`
   and `exhibit\kiosk\start-kiosk.ps1` to `C:\Exhibit`.
2. **Build a release** on a development machine, with the exhibit included:

   ```
   cd exhibit\app && npm ci && npm run build && cd ..\..
   python scripts\v2\build_release.py assemble --release-id 2026-11-02.1 --api-origin https://api.archiveargues.org ^
       --exhibit-app build\exhibit-app --exhibit-deck site\exhibit\deck.json
   python scripts\v2\build_release.py gate --release build\release
   ```

3. **Copy the release to the kiosk** (USB stick or network share) and install it:

   ```
   python C:\Exhibit\serve.py --root C:\Exhibit install D:\release
   ```

4. **Start at sign-in.** In Task Scheduler, run this "At log on" of the kiosk account:

   ```
   powershell -ExecutionPolicy Bypass -File C:\Exhibit\start-kiosk.ps1 -Root C:\Exhibit -Printer
   ```

   Leave out `-Printer` when no receipt printer is attached.
5. **Set up the display.** Turn off sleep and the screen saver, turn on touch, and set the display
   to 100 to 150 percent scaling. The exhibit scales its type to the screen.

## Update and roll back

To install a new release, run `serve.py --root C:\Exhibit install <release folder>` and restart the
kiosk. To roll back to the previous release, run `serve.py --root C:\Exhibit rollback` and restart.
Earlier releases stay in `C:\Exhibit\releases`.

## What the kiosk keeps

The kiosk keeps only daily totals, in `C:\Exhibit\counts\<date>.json`: games started and finished,
and how many times each choice was picked. It records no times of day, no visitors and no answers,
and keeps no access log. The browser runs InPrivate, so it keeps no history, cookies or storage
between restarts. The screen says so on every page: "No personal data is collected. Nothing is
stored."

## Behaviour

- The kiosk opens on the attract screen, the Gap Hunt map walking through the decades. Any touch
  or turn of the dial starts the visit.
- After 60 seconds with no touch, key or turn, the exhibit warns for 10 seconds, then returns to
  the attract screen in English.
- English and French are one touch apart. A "Less motion" switch turns off the attract animation
  and transitions, and the visitor's reduced-motion setting is honoured.
- The dial and the arrow keys move the year. Pressing the dial (Enter) presses the screen's main
  button.
