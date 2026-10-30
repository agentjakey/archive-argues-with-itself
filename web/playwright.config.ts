import { defineConfig, devices } from "@playwright/test";

// End-to-end checks of an assembled static release, with the engine Worker replaced by routes
// inside each test (off, waking, ready). Build the release first:
//   VITE_STATIC_DATA=/data VITE_API_BASE=https://engine.example.test npm run build
//   python scripts/v2/build_release.py assemble --release-id e2e --api-origin https://engine.example.test
// then: npm run e2e        (SCREENSHOTS=1 also writes docs/images/v2/*.png)
export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.e2e.ts",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
    // Settled pages, no fade-ins mid-frame: the site honors reduced motion.
    contextOptions: { reducedMotion: "reduce" },
  },
  projects: [
    { name: "laptop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npx vite preview --outDir ../build/release --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173/release-manifest.json",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
