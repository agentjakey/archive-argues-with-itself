// Editable attract-screen copy and tile selection. Jacob finalizes the hook, the rotating
// questions, and the tile qids. Tiles must be drawn from the already-cached exhibit set (the
// 50 seed + 4 stories) so they are offline-instant, and from questions that do NOT trigger a
// flag or interstitial under the current detection, so the front door stays inviting. The
// six defaults below are answerable, non-flagged seed questions (the flagged ones under the
// current detection are q003/q030/q049); heavier content stays reachable via free-text and
// the stories.

export const ATTRACT_HOOK = "The record argues with itself.";
export const ATTRACT_SUBHOOK =
  "See what the Canadian government said about public health from 1960 to 2009, and when it changed.";

// Display-only teasers, rotated with motion; not tied to a cached question.
export const ATTRACT_QUESTIONS = [
  "How did the government's advice on smoking change over the decades?",
  "What did the record say about health insurance in the 1970s, and by the 1990s?",
  "How did occupational health and safety priorities shift over time?",
  "What changed in how Canada described child care and family health?",
];

// Tile selection: qids from /examples (cached, non-flagged). Order is the tile order.
export const TILE_QIDS = ["q034", "q032", "q033", "q038", "q001", "q027"];

// The payoff label under every tile, so the reward is clear before tapping.
export const TILE_CALLOUT = "See what the government said, and when it changed";

// Decade rail shown in the hero as the change-over-time tease.
export const DECADES = ["1960s", "1970s", "1980s", "1990s", "2000s"];
