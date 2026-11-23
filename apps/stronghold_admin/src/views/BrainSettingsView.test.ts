import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { brainSettingsClient, type BrainSettings } from "../api/BrainSettingsClient";
import BrainSettingsView from "./BrainSettingsView.vue";

const SETTINGS: BrainSettings = {
  stack: { max_items: 40, max_item_chars: 500, compact_item_chars: 1500, warn_ratio: 0.8 },
  long_term: { max_record_chars: 20000, max_files: 500, max_total_bytes: 5000000, search_limit: 8 },
  sharing: { max_share_chars: 20000, max_pending_sent: 30, max_inbox: 100, max_global_queue: 200 },
  ranges: {
    stack: { max_items: [2, 200], max_item_chars: [20, 2000], compact_item_chars: [100, 6000], warn_ratio: [0.3, 0.95] },
    long_term: { max_record_chars: [200, 100000], max_files: [1, 5000], max_total_bytes: [10000, 100000000], search_limit: [1, 30] },
    sharing: { max_share_chars: [200, 100000], max_pending_sent: [1, 200], max_inbox: [1, 1000], max_global_queue: [1, 1000] },
  },
  root: "/data/brain",
  stored: { stack: false, long_term: true, sharing: false },
};

beforeEach(() => {
  vi.spyOn(brainSettingsClient, "get").mockResolvedValue(SETTINGS);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(BrainSettingsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
type Wrapper = Awaited<ReturnType<typeof mounted>>;
const field = (wrapper: Wrapper, name: string) => wrapper.get(`[data-test="${name}"]`);
const save = (wrapper: Wrapper) => wrapper.get('[data-test="save"]');
const submit = async (wrapper: Wrapper) => {
  await wrapper.get('[data-test="save"]').trigger("click");
  await flushPromises();
};

describe("BrainSettingsView", () => {
  it("shows every limit with its range, where the files are kept, and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("500");
    expect(field(wrapper, "long_term.max_files").attributes("min")).toBe("1");
    expect(field(wrapper, "long_term.max_files").attributes("max")).toBe("5000");
    expect((field(wrapper, "stack.warn_ratio").element as HTMLInputElement).value).toBe("0.8");
    expect((field(wrapper, "sharing.max_inbox").element as HTMLInputElement).value).toBe("100");
    expect(wrapper.text()).toContain("/data/brain");
    await wrapper.get('[data-test="panel-help"]').trigger("click");
    expect(document.body.textContent).toContain("STRONGHOLD_BRAIN_ROOT");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("says which parts were changed from the defaults", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="state-long_term"]').text()).toContain("changed from the defaults");
    expect(wrapper.get('[data-test="state-stack"]').text()).toContain("defaults");
    expect(wrapper.get('[data-test="state-stack"]').text()).not.toContain("changed");
    wrapper.unmount();
  });

  it("shows the size a byte limit means", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="hint-long_term.max_total_bytes"]').text()).toContain("5.0 MB");
    await field(wrapper, "long_term.max_total_bytes").setValue("250000");
    expect(wrapper.get('[data-test="hint-long_term.max_total_bytes"]').text()).toContain("250 KB");
    wrapper.unmount();
  });

  it("sends only the field that changed", async () => {
    const send = vi.spyOn(brainSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect(send).toHaveBeenCalledExactlyOnceWith({ long_term: { max_files: 50 } });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("Stronghold uses it now");
    wrapper.unmount();
  });

  it("sends changes from several parts, each with only its changed fields, and numbers not text", async () => {
    const send = vi.spyOn(brainSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await field(wrapper, "stack.warn_ratio").setValue("0.9");
    await field(wrapper, "stack.max_items").setValue("60");
    await field(wrapper, "sharing.max_inbox").setValue("50");
    await submit(wrapper);
    expect(send).toHaveBeenCalledExactlyOnceWith({ stack: { max_items: 60, warn_ratio: 0.9 }, sharing: { max_inbox: 50 } });
    wrapper.unmount();
  });

  it("does not count 040 for 40 as a change", async () => {
    const wrapper = await mounted();
    await field(wrapper, "stack.max_items").setValue("040");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("lets the Save button submit a warning ratio anywhere in the server range", async () => {
    const send = vi.spyOn(brainSettingsClient, "save").mockResolvedValue(SETTINGS);
    const wrapper = await mounted();
    await field(wrapper, "stack.warn_ratio").setValue("0.83");
    (save(wrapper).element as HTMLButtonElement).click();
    await flushPromises();
    expect(send).toHaveBeenCalledExactlyOnceWith({ stack: { warn_ratio: 0.83 } });
    wrapper.unmount();
  });

  it("shows what is wrong with a value, in words, and keeps Save off", async () => {
    const wrapper = await mounted();
    await field(wrapper, "stack.max_items").setValue("1");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("2 to 200");
    expect(field(wrapper, "stack.max_items").attributes("aria-invalid")).toBe("true");
    expect(field(wrapper, "stack.max_items").attributes("aria-describedby")).toContain("problem");
    await wrapper.get('[data-test="save"]').trigger("click");
    expect(wrapper.get('[role="alert"]').text()).toContain("highlighted");
    await field(wrapper, "stack.max_items").setValue("2.5");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("whole number");
    await field(wrapper, "stack.max_items").setValue("");
    expect(wrapper.get('[data-test="problem-stack.max_items"]').text()).toContain("Enter a number");
    await field(wrapper, "stack.max_items").setValue("40");
    expect(wrapper.find('[data-test="problem-stack.max_items"]').exists()).toBe(false);
    await field(wrapper, "stack.warn_ratio").setValue("0.2");
    expect(wrapper.get('[data-test="problem-stack.warn_ratio"]').text()).toContain("0.3 to 0.95");
    await field(wrapper, "stack.warn_ratio").setValue("0.5");
    expect(wrapper.find('[data-test="problem-stack.warn_ratio"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows the server's refusal as it came and keeps the edits", async () => {
    vi.spyOn(brainSettingsClient, "save").mockRejectedValue(new Error("max_files must be a whole number from 1 to 5000."));
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toBe("max_files must be a whole number from 1 to 5000.");
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("50");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("takes the server's answer as the new saved state", async () => {
    const after: BrainSettings = { ...SETTINGS, long_term: { ...SETTINGS.long_term, max_files: 50 }, stored: { stack: false, long_term: true, sharing: false } };
    vi.spyOn(brainSettingsClient, "save").mockResolvedValue(after);
    const wrapper = await mounted();
    await field(wrapper, "long_term.max_files").setValue("50");
    await submit(wrapper);
    expect((field(wrapper, "long_term.max_files").element as HTMLInputElement).value).toBe("50");
    expect(wrapper.find('[data-test="save"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("hides the Sharing card when Stronghold does not report sharing", async () => {
    const { sharing: _sharing, ...rest } = SETTINGS;
    vi.spyOn(brainSettingsClient, "get").mockResolvedValue({ ...rest, stored: { stack: false, long_term: true } });
    const wrapper = await mounted();
    expect(wrapper.find('[data-test="sharing.max_inbox"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="stack.max_items"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("a failed load shows the reason with a way to try again", async () => {
    vi.spyOn(brainSettingsClient, "get").mockRejectedValueOnce(new Error("Storage is unavailable"));
    const wrapper = await mounted();
    expect(wrapper.get('[role="alert"]').text()).toContain("Storage is unavailable");
    expect(wrapper.find('[data-test="form"]').exists()).toBe(false);
    await wrapper.get('[data-test="retry"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-test="form"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
