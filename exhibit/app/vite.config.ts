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
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
