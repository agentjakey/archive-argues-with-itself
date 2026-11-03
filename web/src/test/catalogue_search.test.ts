import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, expect, test } from "vitest";

const source = readFileSync(resolve("../site/catalogue/catalogue.js"), "utf-8");
let matches: (doc: object) => boolean;
const doc = { t: "Annual report on tuberculosis", i: "Ontario Health", p: "ontario", s: ["known"], c: ["health"] };

beforeEach(() => {
  document.body.innerHTML = '<input id="text"><input id="place"><input id="state"><input id="collection">';
  // Exercise the shipped static script; leave its initial data load pending, without network calls.
  matches = new Function("document", "URL", "window", "fetch", `${source}\nreturn matches;`)(
    document, URL, {}, () => new Promise(() => {}),
  );
});

test.each([
  ["tuberculosis annual", true],
  ["annual tuberculosis", true],
  ["  TUBERCULOSIS   ANNUAL\t", true],
  ["health tuberculosis", true],
  ["annual cholera", false],
  ["tuberculosis", true],
  ["", true],
  [" \t ", true],
])("catalogue query %j matches: %s", (query, expected) => {
  (document.getElementById("text") as HTMLInputElement).value = query;
  expect(matches(doc)).toBe(expected);
});

test("word matching still respects the other filters and missing issuers", () => {
  (document.getElementById("text") as HTMLInputElement).value = "tuberculosis annual";
  expect(matches({ ...doc, i: null })).toBe(true);
  for (const [id, value] of [["place", "federal"], ["state", "indexed"], ["collection", "other"]]) {
    const input = document.getElementById(id) as HTMLInputElement;
    input.value = value;
    expect(matches(doc)).toBe(false);
    input.value = "";
  }
});
