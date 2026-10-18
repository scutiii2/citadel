import { describe, expect, it } from "vitest";
import { CREATE_MODE_OPTIONS, FULL_AUTO_PHRASE, MODE_HELP, MODE_OPTIONS } from "./forgeModes";

describe("forge modes", () => {
  it("offers the four modes in order, and full auto only after creation", () => {
    expect(MODE_OPTIONS.map((o) => o.value)).toEqual(["ask", "accept_edits", "plan", "full_auto"]);
    expect(CREATE_MODE_OPTIONS.map((o) => o.value)).toEqual(["ask", "accept_edits", "plan"]);
  });

  it("explains every mode, including what Codex does", () => {
    for (const option of MODE_OPTIONS) expect(MODE_HELP[option.value].length).toBeGreaterThan(20);
    expect(MODE_HELP.ask).toContain("Codex");
    expect(FULL_AUTO_PHRASE).toBe("full auto");
  });
});
