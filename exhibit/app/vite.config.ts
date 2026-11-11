import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The exhibit is served at /exhibit/ by the site Worker and from the kiosk's own local server.
// Every asset path is relative to that base; the deck is read from ./decks/current.json.
export default defineConfig({
  base: "/exhibit/",
  plugins: [react()],
  build: {
    outDir: "../../build/exhibit-app",
    emptyOutDir: true,
    sourcemap: false,
    // Vite 7 moved the default target to "baseline-widely-available" (Chrome and Edge 107, Firefox
    // 104, Safari 16); the exhibit keeps Vite 5's default targets so the browsers it ran on still do.
    target: ["es2020", "edge88", "firefox78", "chrome87", "safari14"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
