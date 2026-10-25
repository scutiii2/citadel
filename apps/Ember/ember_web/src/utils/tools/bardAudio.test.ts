import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../api/types";
import { bardFileIds } from "./bardAudio";

const FID = "a".repeat(32);
const step = (tool: string, result: string, ok: boolean | null = true): ToolStep => ({
  tool, label: tool, arguments: {}, ok, result,
});

describe("bardFileIds", () => {
  it("returns the file id of a successful speak step, namespace included", () => {
    const steps = [step("bard__tool_bard_speak", JSON.stringify({ file_id: FID, message: "ok" }))];
    expect(bardFileIds(steps)).toEqual([FID]);
  });

  it("ignores other tools, failed or running steps and results without a file id", () => {
    expect(bardFileIds([
      step("tool_pdf_merge", JSON.stringify({ file_id: FID })),
      step("bard__tool_bard_speak", JSON.stringify({ file_id: FID }), false),
      step("bard__tool_bard_speak", "", null),
      step("bard__tool_bard_speak", "not json"),
      step("bard__tool_bard_speak", JSON.stringify({ file_id: 7 })),
    ])).toEqual([]);
  });

  it("lists each file once, in order", () => {
    const other = "b".repeat(32);
    const speak = (id: string) => step("bard__tool_bard_speak", JSON.stringify({ file_id: id }));
    expect(bardFileIds([speak(FID), speak(other), speak(FID)])).toEqual([FID, other]);
  });

  it("accepts no steps", () => {
    expect(bardFileIds(undefined)).toEqual([]);
  });
});
