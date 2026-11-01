import { defineConfig, devices } from "@playwright/test";

// End-to-end checks of the exhibit as a kiosk serves it: the assembled release, installed into a
// test kiosk folder and served by exhibit/kiosk/serve.py with the release's own headers. First:
//   python scripts/v2/build_release.py assemble --release-id e2e --api-origin https://engine.example.test \
//       --exhibit-app build/exhibit-app --exhibit-deck site/exhibit/deck.json
//   python exhibit/kiosk/serve.py --root build/kiosk-e2e install build/release
// then: npx playwright test   (SCREENSHOTS=1 writes docs/images/exhibit/*.png; the full-visit test
// records a video into test-results/)
const PYTHON = process.env.PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.e2e.ts",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8799",
    trace: "off",
  },
  projects: [
    { name: "kiosk", use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 }, hasTouch: true } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `${PYTHON} ../kiosk/serve.py --root ../../build/kiosk-e2e --port 8799 --printer`,
    url: "http://127.0.0.1:8799/exhibit/kiosk.json",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
