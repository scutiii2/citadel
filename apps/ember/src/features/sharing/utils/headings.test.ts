import { describe, expect, it } from "vitest";
import { headingsOf } from "./headings";

describe("headingsOf", () => {
  it("lists the headings in order, at any level", () => {
    expect(headingsOf("# One\ntext\n## Two\n### Three")).toEqual(["One", "Two", "Three"]);
  });

  it("needs a space after the marks", () => {
    expect(headingsOf("#hashtag\n####### seven\n# Real")).toEqual(["Real"]);
  });

  it("drops closing marks and extra spaces", () => {
    expect(headingsOf("##   Brewing   tea  ##")).toEqual(["Brewing tea"]);
  });

  it("skips headings inside fenced code, however the fence is written", () => {
    const body = "# A\n```\n# not one\n```\n~~~js\n# nor this\n~~~\n## B\n````\n```\n# still code\n````\n# C";
    expect(headingsOf(body)).toEqual(["A", "B", "C"]);
  });

  it("keeps the first of repeated headings, ignoring case and spacing", () => {
    expect(headingsOf("# Notes\n## notes\n#  NOTES \n# Other")).toEqual(["Notes", "Other"]);
  });

  it("uses the server’s exact line and whitespace boundaries", () => {
    expect(headingsOf("# One\r## Two\u2028### Three\n# A\u0085# B")).toEqual(["One ## Two ### Three", "A # B"]);
    expect(headingsOf("# A\u001fB\n# A B")).toEqual(["A B"]);
  });

  it("copes with Windows line ends and an empty text", () => {
    expect(headingsOf("# One\r\ntext\r\n## Two\r\n")).toEqual(["One", "Two"]);
    expect(headingsOf("")).toEqual([]);
  });
});
