import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../api/types";
import { bardClips } from "./bardAudio";

const FID = "a".repeat(32);
const step = (tool: string, result: string, ok: boolean | null = true): ToolStep => ({
  tool, label: tool, arguments: {}, ok, result,
});

describe("bardClips", () => {
  it("returns the file, voice and length of a successful speak step, namespace included", () => {
    const steps = [step("bard__tool_bard_speak", JSON.stringify({ file_id: FID, voice: "en_US-lessac-medium", duration_s: 2.04 }))];
    expect(bardClips(steps)).toEqual([{ fileId: FID, voice: "en_US-lessac-medium", durationS: 2.04 }]);
  });

  it("leaves the voice and length empty when the result lacks them", () => {
    const steps = [step("bard__tool_bard_speak", JSON.stringify({ file_id: FID, voice: 3, duration_s: "long" }))];
    expect(bardClips(steps)).toEqual([{ fileId: FID, voice: "", durationS: null }]);
  });

  it("ignores other tools, failed or running steps and results without a file id", () => {
    expect(bardClips([
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
    expect(bardClips([speak(FID), speak(other), speak(FID)]).map((c) => c.fileId)).toEqual([FID, other]);
  });

  it("accepts no steps", () => {
    expect(bardClips(undefined)).toEqual([]);
  });
});
