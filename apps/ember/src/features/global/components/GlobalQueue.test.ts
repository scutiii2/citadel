import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Share } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import GlobalQueue from "./GlobalQueue.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { queue: vi.fn() },
}));
vi.mock("./GlobalReview.vue", () => ({
  default: {
    props: ["share"],
    emits: ["close", "done"],
    template: '<div data-test="review">{{ share.title }}<button data-test="finish" @click="$emit(\'done\', \'Rejected.\')">finish</button></div>',
  },
}));
const client = vi.mocked(globalClient);

const share = (id: string, title: string): Share => ({
  id, kind: "file", title, status: "pending", sender: "bo", recipient: "global brain",
  created_at: "2026-01-01T00:00:00Z", decided_at: null, result_id: null, chars: 9,
});

let wrapper: VueWrapper | null = null;
async function mountIt() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount({ permissions: ["chat.use", "brain.global.write"] });
  wrapper = mount(GlobalQueue, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
beforeEach(() => {
  vi.clearAllMocks();
  client.queue.mockResolvedValue([share("s1", "Tea notes"), share("s2", "Metric units")]);
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalQueue", () => {
  it("lists what waits and says when nothing does", async () => {
    const w = await mountIt();
    expect(w.text()).toContain("Tea notes");
    expect(w.text()).toContain("Metric units");
    wrapper?.unmount();
    client.queue.mockResolvedValue([]);
    expect((await mountIt()).text()).toContain("Nothing is waiting for review.");
  });

  it("opens a review on a row click and reloads with a note after it is done", async () => {
    const w = await mountIt();
    await w.findAll("button").find((b) => b.text().includes("Metric units"))!.trigger("click");
    expect(w.get("[data-test='review']").text()).toContain("Metric units");
    client.queue.mockClear();
    client.queue.mockResolvedValue([share("s1", "Tea notes")]);
    await w.get("[data-test='finish']").trigger("click");
    await flushPromises();
    expect(w.find("[data-test='review']").exists()).toBe(false);
    expect(w.get("[role='status']").text()).toContain("Rejected.");
    expect(client.queue).toHaveBeenCalled();
    expect(w.text()).not.toContain("Metric units");
  });

  it("shows an error and retries", async () => {
    client.queue.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt();
    expect(w.text()).toContain("Storage is unavailable");
    await w.findAll("button").find((b) => b.text() === "Try again")!.trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Tea notes");
  });
});
