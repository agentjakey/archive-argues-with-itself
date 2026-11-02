import { defineConfig, devices } from "@playwright/test";

// End-to-end checks of the exhibit as a kiosk serves it: the assembled release, installed into a
// test kiosk folder and served by exhibit/kiosk/serve.py with the release's own headers. First:
//   npm run build
//   python scripts/v2/build_release.py assemble --release-id e2e --api-origin https://engine.example.test \
//       --exhibit-app build/exhibit-app --exhibit-deck site/exhibit/deck.json
//   python exhibit/kiosk/serve.py --root build/kiosk-e2e install build/release
// then: npx playwright test
// With EVIDENCE=<folder> the run also writes a screenshot of every screen per size, the axe results
// and a video of one full visit into that folder (reports/v2/exhibit/redesign is the usual one).
const PYTHON = process.env.PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.e2e.ts",
  timeout: 180_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8799",
    trace: "off",
  },
  projects: [
    { name: "kiosk", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 }, hasTouch: true } },
    { name: "uhd", use: { ...devices["Desktop Chrome"], viewport: { width: 3840, height: 2160 }, hasTouch: true } },
    {
      name: "phone",
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 }, screen: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: `${PYTHON} ../kiosk/serve.py --root ../../build/kiosk-e2e --port 8799 --printer`,
    url: "http://127.0.0.1:8799/exhibit/kiosk.json",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
