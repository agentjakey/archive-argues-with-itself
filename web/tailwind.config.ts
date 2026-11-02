import type { Config } from "tailwindcss";

// The reading room in Agora's look. Every colour is a token from design/tokens.css (shared with the
// catalogue and the exhibit), so the theme names below are roles, not values:
//   paper = the ground, sheet = a surface, ink = body text, muted = secondary text,
//   rule = a decorative hairline, accent = the gold (links, focus, the cited mark).
// split-a and split-b mark the two records of a comparison. Corners are square (1 px at most) and
// nothing casts a shadow.
const token = (name: string) => `rgb(var(--${name}-rgb) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: token("bg"),
        sheet: token("surface"),
        ink: token("text"),
        muted: token("muted"),
        rule: token("hair"),
        line: token("line"),
        accent: token("gold"),
        gold: token("gold"),
        "split-a": token("split-a"),
        "split-b": token("split-b"),
      },
      fontFamily: {
        serif: ["Crimson Text", "Georgia", "Times New Roman", "serif"],
        sans: ["Crimson Text", "Georgia", "Times New Roman", "serif"],
        display: ["Cinzel", "Trajan Pro", "Georgia", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "Menlo", "monospace"],
      },
      maxWidth: { prose: "70ch" },
    },
    borderRadius: {
      none: "0",
      sm: "1px",
      DEFAULT: "1px",
      md: "1px",
      lg: "1px",
      xl: "1px",
      full: "1px",
    },
    boxShadow: {
      none: "none",
      sm: "none",
      DEFAULT: "none",
      md: "none",
      lg: "none",
      xl: "none",
    },
  },
  plugins: [],
} satisfies Config;
