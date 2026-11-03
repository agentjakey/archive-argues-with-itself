import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vitest/config";
import react from "@vitejs/plugin-react";

const API = "http://127.0.0.1:8000";
const DESIGN = fileURLToPath(new URL("../design/", import.meta.url));

/** Publishes the shared design tokens (design/tokens.css, theme-light.css, theme-boot.js) and their
 *  fonts at the site root, as /tokens.css, /theme-light.css, /theme-boot.js and /fonts/*, for the
 *  static pages outside the app (the catalogue links them).
 *  The app itself imports the same file through src/styles.css, so there is one token file. */
function sharedTokens(): Plugin {
  return {
    name: "shared-design-tokens",
    // The theme boot script is a separate file (the Content-Security-Policy allows no inline script):
    // index.html loads /theme-boot.js, served here in development and emitted at the root in a build.
    configureServer(server) {
      server.middlewares.use("/theme-boot.js", (_req, res) => {
        res.setHeader("content-type", "text/javascript");
        res.end(readFileSync(`${DESIGN}theme-boot.js`));
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "tokens.css", source: readFileSync(`${DESIGN}tokens.css`) });
      this.emitFile({ type: "asset", fileName: "theme-light.css", source: readFileSync(`${DESIGN}theme-light.css`) });
      this.emitFile({ type: "asset", fileName: "theme-boot.js", source: readFileSync(`${DESIGN}theme-boot.js`) });
      for (const name of readdirSync(`${DESIGN}fonts`)) {
        this.emitFile({ type: "asset", fileName: `fonts/${name}`, source: readFileSync(`${DESIGN}fonts/${name}`) });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), sharedTokens()],
  server: {
    proxy: {
      "/ask": API,
      "/coverage": API,
      "/examples": API,
      "/health": API,
    },
    fs: { allow: [".", "../design"] },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
