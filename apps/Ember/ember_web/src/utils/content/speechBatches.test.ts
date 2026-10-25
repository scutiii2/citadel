import { expect, it } from "vitest";
import { speechBatches } from "./speechBatches";

it("strips markdown, links and code fences before speaking", () => {
  expect(speechBatches("# Hello\n**world** and [friends](https://example.com).\n```js\nsecret()\n```\n`Goodbye`.")).toEqual(["Hello world and friends. Goodbye."]);
});
it("skips code-only and empty messages", () => {
  expect(speechBatches("  ")).toEqual([]);
  expect(speechBatches("```python\nprint(1)\n```")).toEqual([]);
});
it("groups sentences without breaking abbreviations", () => {
  expect(speechBatches("Dr. Smith arrived. Next sentence! Last?", 22)).toEqual(["Dr. Smith arrived.", "Next sentence! Last?"]);
  expect(speechBatches("Use e.g. apples. Done.", 16)).toEqual(["Use e.g. apples.", "Done."]);
});
it("splits one huge sentence at whitespace under 3500 characters", () => {
  const text = "word ".repeat(2000).trim();
  const batches = speechBatches(text);
  expect(batches.length).toBe(3);
  expect(batches.every((batch) => batch.length <= 3500)).toBe(true);
  expect(batches.join(" ")).toBe(text);
});
it("hard splits a huge word and never emits empty batches", () => {
  expect(speechBatches("x".repeat(7001)).map((b) => b.length)).toEqual([3500, 3500, 1]);
});
it("keeps sentence boundaries when the next sentence would overflow", () => {
  expect(speechBatches("Hello there. How are you? Fine!", 25)).toEqual(["Hello there. How are you?", "Fine!"]);
});
it("handles fenced variants, HTML and reference links as plain text", () => {
  expect(speechBatches("~~~js\nhidden()\n~~~\n<b>Hello</b> [world][w].\n\n[w]: https://example.com")).toEqual(["Hello world."]);
});
