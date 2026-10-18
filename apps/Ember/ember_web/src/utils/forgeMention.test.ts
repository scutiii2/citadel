import { describe, expect, it } from "vitest";
import { completeMention, matchingLabels, mentionAt } from "./forgeMention";

describe("mentionAt", () => {
  it("finds the handle being typed", () => {
    expect(mentionAt("@cl", 3)).toEqual({ start: 0, query: "cl" });
    expect(mentionAt("please ask @co", 14)).toEqual({ start: 11, query: "co" });
    expect(mentionAt("hey @", 5)).toEqual({ start: 4, query: "" });
  });

  it("only looks before the caret", () => {
    expect(mentionAt("@claude later", 3)).toEqual({ start: 0, query: "cl" });
    expect(mentionAt("@claude", 0)).toBeNull();
  });

  it("is not a mention inside a word or an address, or after the handle ends", () => {
    expect(mentionAt("mail me at a@cl", 15)).toBeNull();
    expect(mentionAt("@claude hi", 10)).toBeNull();
    expect(mentionAt("no at sign", 5)).toBeNull();
  });

  it("allows the handle characters only", () => {
    expect(mentionAt("@code-rev_2", 11)).toEqual({ start: 0, query: "code-rev_2" });
    expect(mentionAt("@co!", 4)).toBeNull();
  });
});

describe("matchingLabels", () => {
  it("matches by prefix, ignoring case, in the given order", () => {
    expect(matchingLabels(["claude", "codex", "Cursor"], "c")).toEqual(["claude", "codex", "Cursor"]);
    expect(matchingLabels(["claude", "codex"], "CO")).toEqual(["codex"]);
    expect(matchingLabels(["claude", "codex"], "")).toEqual(["claude", "codex"]);
    expect(matchingLabels(["claude"], "x")).toEqual([]);
  });
});

describe("completeMention", () => {
  it("replaces the typed part and puts the caret after the space", () => {
    const text = "please ask @co about it";
    const mention = mentionAt(text, 14)!;

    expect(completeMention(text, mention, 14, "codex")).toEqual({ text: "please ask @codex  about it", caret: 18 });
  });

  it("works at the start and at the end", () => {
    expect(completeMention("@c", { start: 0, query: "c" }, 2, "claude")).toEqual({ text: "@claude ", caret: 8 });
  });
});
