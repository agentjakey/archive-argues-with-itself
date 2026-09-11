import type { Config } from "tailwindcss";

// Reading room, not chat: paper and ink, one accent reserved for "Cited".
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f6f1e7",
        sheet: "#fcfaf4",
        ink: "#1c1a17",
        muted: "#6b655c",
        rule: "#d9d2c3",
        accent: "#8b2e1f",
      },
      fontFamily: {
        serif: ["Iowan Old Style", "Charter", "Georgia", "Times New Roman", "serif"],
        sans: ["system-ui", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "Menlo", "monospace"],
      },
      maxWidth: { prose: "70ch" },
    },
  },
  plugins: [],
} satisfies Config;
