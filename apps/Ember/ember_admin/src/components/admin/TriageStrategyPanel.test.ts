import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { triageStrategyClient } from "../../api/TriageStrategyClient";
import TriageStrategyPanel from "./TriageStrategyPanel.vue";

vi.mock("../../api/TriageStrategyClient", () => ({
  triageStrategyClient: { get: vi.fn(), set: vi.fn() },
}));

const NAMES = ["english-only", "typed-only", "auto"];

beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: null, strategies: NAMES });
    vi.mocked(triageStrategyClient.set).mockImplementation(async (value) => ({ default: value, strategies: NAMES }));
});

describe("TriageStrategyPanel", () => {
  it("lists 'not set' first and then the service's strategies", async () => {
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    const options = w.findAll("option").map((o) => o.text());
    expect(options[0]).toMatch(/not set/i);
    expect(options.slice(1)).toEqual(NAMES);
  });

  it("saves only after Save and shows the stored value once the server answers", async () => {
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    await w.find("select").setValue("typed-only");
    expect(triageStrategyClient.set).not.toHaveBeenCalled();
    await w.find("button.primary").trigger("click");
    await flushPromises();
    expect(triageStrategyClient.set).toHaveBeenCalledWith("typed-only");
    expect(w.emitted("modified")?.at(-1)).toEqual([true]);
    expect(w.find(".save-bar").exists()).toBe(false);
  });

  it("keeps the draft and shows the error when the save fails", async () => {
    vi.mocked(triageStrategyClient.set).mockRejectedValue(new Error("ai_agent is unreachable"));
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    await w.find("select").setValue("auto");
    await w.find("button.primary").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("ai_agent is unreachable");
    expect((w.find("select").element as HTMLSelectElement).value).toBe("auto");
  });

  it("offers nothing to pick while the service list is empty", async () => {
    vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: "typed-only", strategies: [] });
    const w = mount(TriageStrategyPanel);
    await flushPromises();
    expect(w.text()).toContain("typed-only");
    expect(w.find("select").attributes("disabled")).toBeDefined();
  });
});


it("keeps Save pending and the stored state unchanged until the server answers", async () => {
  let finish!: (value: { default: string | null; strategies: string[] }) => void;
  vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: null, strategies: NAMES });
  vi.mocked(triageStrategyClient.set).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  const w = mount(TriageStrategyPanel);
  await flushPromises();
  await w.get("select").setValue("auto");
  await w.get("button.primary").trigger("click");
  expect(w.get("button.primary").attributes("disabled")).toBeDefined();
  expect(w.get("button.primary").attributes("aria-busy")).toBe("true");
  expect(w.emitted("modified")?.at(-1)).toEqual([false]);
  finish({ default: "auto", strategies: NAMES });
  await flushPromises();
  expect(w.emitted("modified")?.at(-1)).toEqual([true]);
  expect(w.find(".save-bar").exists()).toBe(false);
});

it("cancels a draft and clears an existing default with null only on Save", async () => {
  vi.mocked(triageStrategyClient.get).mockResolvedValue({ default: "typed-only", strategies: NAMES });
  vi.mocked(triageStrategyClient.set).mockResolvedValue({ default: null, strategies: NAMES });
  const w = mount(TriageStrategyPanel);
  await flushPromises();
  await w.get("select").setValue("");
  await w.get("button.small").trigger("click");
  expect((w.get("select").element as HTMLSelectElement).value).toBe("typed-only");
  await w.get("select").setValue("");
  await w.get("button.primary").trigger("click");
  await flushPromises();
  expect(triageStrategyClient.set).toHaveBeenLastCalledWith(null);
  expect(w.emitted("modified")?.at(-1)).toEqual([false]);
});
