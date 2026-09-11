# Screenshots

Three PNGs referenced by the top-level README. Take them from the built app
served by the API (`python -m uvicorn archive_debugger.api.app:app`) with the
answer cache warm, at a 1440 x 900 viewport, light theme, browser chrome
cropped out, saved as PNG at 2x device pixel ratio if available.

| file | state | URL |
| --- | --- | --- |
| `hero.png` | Answered question: the answer with numbered citation marks and the Sources list, the decade timeline, and the first evidence cards visible. Scroll so the answer heading is at the top. | `/?q=How+did+Alberta+health+insurance+coverage+change+between+the+1970s+and+1990s%3F&jurisdiction=alberta` |
| `abstention.png` | Abstention card with the coverage grid directly beneath it ("Why the record is thin here"), zeros visible in the grid. | `/?q=What+did+public+health+authorities+report+about+the+COVID-19+pandemic+in+2020%3F` |
| `compare.png` | Compare view open from a story: two pages side by side, years as column headers, the story caption above. Open the first story from the home screen, then scroll so the compare heading is at the top. | `/` then click the first story |

Optional fourth for the exhibit docs: `kiosk.png`, the home screen at
`/?kiosk=1&offline=1` on a 1920 x 1080 viewport showing the stories.
