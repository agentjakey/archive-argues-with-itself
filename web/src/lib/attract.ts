// Editable attract-screen copy and tile selection. Jacob finalizes the hook and the tile qids.
// Tiles must be drawn from the already-cached exhibit set (the 50 seed + 4 stories) so they are
// offline-instant, and from questions that do NOT trigger a flag or interstitial under the current
// detection, so the front door stays inviting. The six defaults below are answerable, non-flagged
// seed questions (the flagged ones under the current detection are q003/q030/q049); heavier content
// stays reachable via free-text and the stories.

// The static hook, shown when a corpus ships no curated stories to lead with (the landing hero
// otherwise leads with a real curated example, not a slogan).
export const ATTRACT_HOOK = "The record argues with itself.";
export const ATTRACT_SUBHOOK =
  "See what the Canadian government said about public health from 1960 to 2009, and when it changed.";

// Tile selection: qids from /examples (cached, non-flagged). Order is the tile order.
export const TILE_QIDS = ["q034", "q032", "q033", "q038", "q001", "q027"];

// The payoff label under every tile, so the reward is clear before tapping.
export const TILE_CALLOUT = "See what the government said, and when it changed";
