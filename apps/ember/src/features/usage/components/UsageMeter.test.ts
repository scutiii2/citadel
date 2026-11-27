import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { usageClient, type MyUsage } from "../api/UsageClient";
import type { UsageWindow } from "../../../api/contracts/usage";
import { useAuthStore } from "../../../stores/auth";
import { useUsageLimitsStore } from "../stores/usageLimits";
import UsageMeter from "./UsageMeter.vue";

vi.mock("../api/UsageClient", () => ({ usageClient: { mine: vi.fn() } }));
const mine = vi.mocked(usageClient.mine);

const window = (used: number, limit: number, reset_at: string | null = null): UsageWindow => ({ used, limit, reset_at });
const usage = (six: UsageWindow, week: UsageWindow): MyUsage => ({ six_hour: six, weekly: week, report: {} as MyUsage["report"] });
const account = (id: number) => ({ id, username: "alice", email: "a@example.com", email_verified: true, roles: [], permissions: [] });

beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = account(1);
  mine.mockReset();
  mine.mockResolvedValue(usage(window(25_000, 100_000), window(900_000, 1_000_000, "2026-11-28T10:00:00")));
});
afterEach(() => {
  document.body.innerHTML = "";
});

async function setup(props: { detailsLink?: boolean } = {}) {
  const stub = { template: "<div />" };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: stub }, { path: "/usage", component: stub }] });
  await router.push("/");
  const wrapper = mount(UsageMeter, { props: { detailsLink: true, ...props }, global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return { wrapper, router };
}
const button = (wrapper: Awaited<ReturnType<typeof setup>>["wrapper"]) => wrapper.get("button.meter");

describe("UsageMeter", () => {
  it("shows the fuller of the two limits on the ring and names both", async () => {
    const { wrapper } = await setup();

    expect(wrapper.get(".arc").attributes("stroke-dasharray")).toBe("90 100");
    expect(wrapper.get(".ring").classes()).toContain("danger");
    expect(button(wrapper).attributes("aria-label")).toBe("Usage limits: last 6 hours 25%, last 7 days 90%, almost used up");
  });

  it("opens the numbers with a link to the Usage page, and reads them again", async () => {
    const { wrapper } = await setup();
    expect(wrapper.find(".panel").exists()).toBe(false);

    await button(wrapper).trigger("click");
    await flushPromises();

    expect(button(wrapper).attributes("aria-expanded")).toBe("true");
    const panel = wrapper.get(".panel").text();
    expect(panel).toContain("25,000 of 100,000 tokens");
    expect(panel).toContain("Oldest tokens stop counting at");
    expect(wrapper.get('.panel a[href="/usage"]').text()).toBe("Usage details");
    expect(mine).toHaveBeenCalledTimes(2);
  });

  it("has no link when the account cannot open the Usage page", async () => {
    const { wrapper } = await setup({ detailsLink: false });
    await button(wrapper).trigger("click");

    expect(wrapper.find(".panel a").exists()).toBe(false);
  });

  it("closes on Escape, on a press outside and on a page change", async () => {
    const { wrapper, router } = await setup();
    const open = async () => button(wrapper).trigger("click");

    await open();
    await wrapper.get(".usage-meter").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".panel").exists()).toBe(false);

    await open();
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(wrapper.find(".panel").exists()).toBe(false);

    await open();
    await router.push("/usage");
    await flushPromises();
    expect(wrapper.find(".panel").exists()).toBe(false);
  });

  it("is not shown when no limit is set or the usage cannot be read", async () => {
    mine.mockResolvedValue(usage(window(5, 0), window(5, 0)));
    expect((await setup()).wrapper.find("button").exists()).toBe(false);

    setActivePinia(createPinia());
    useAuthStore().account = account(1);
    mine.mockRejectedValue(new Error("down"));
    expect((await setup()).wrapper.find("button").exists()).toBe(false);
  });

  it("never shows one account the numbers of another", async () => {
    const { wrapper } = await setup();
    mine.mockReturnValue(new Promise(() => undefined));

    useAuthStore().account = account(2);
    await flushPromises();

    expect(useUsageLimitsStore().windows).toEqual([]);
    expect(wrapper.find("button").exists()).toBe(false);
  });
});
