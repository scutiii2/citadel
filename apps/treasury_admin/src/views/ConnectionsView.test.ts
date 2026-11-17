import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { treasuryAdminClient, type ConnectionsView } from "../api/TreasuryAdminClient";
import ConnectionsViewPage from "./ConnectionsView.vue";

const VIEW: ConnectionsView = {
  connections: [
    { name: "data", spec: { type: "sqlite", path: "ember.db" }, source: "built-in", used_by: ["ember"] },
    { name: "main", spec: { type: "sqlite", path: "mine.db" }, source: "changed", used_by: [] },
    { name: "reports", spec: { type: "postgres", dsn: "${REPORTS_DSN}" }, source: "saved", used_by: ["legion"] },
  ],
  default_cache: { ttl_seconds: 30, max_entries: 1000, negative_ttl_seconds: 5 },
  default_cache_stored: false,
};

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
});
beforeEach(() => {
  vi.spyOn(treasuryAdminClient, "connections").mockResolvedValue(VIEW);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(ConnectionsViewPage, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe("ConnectionsView", () => {
  it("lists the connections with where they come from and who uses them", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-data"]').text()).toContain("built-in");
    expect(wrapper.get('[data-test="row-data"]').text()).toContain("ember");
    expect(wrapper.get('[data-test="row-main"]').text()).toContain("changed");
    expect(wrapper.get('[data-test="row-reports"]').text()).toContain("${REPORTS_DSN}");
    expect(wrapper.find('[data-test="row-data"] [data-test="remove"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("adds a SQLite connection and says it is offered at once", async () => {
    const save = vi.spyOn(treasuryAdminClient, "saveConnection").mockResolvedValue({ ...VIEW, applies: "now" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="name"]').setValue("scratch2");
    await wrapper.get('[data-test="path"]').setValue("scratch2.db");
    await wrapper.get('[data-test="raw-sql"]').setValue(true);
    await wrapper.get('[data-test="cache"]').setValue("0");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("scratch2", { type: "sqlite", path: "scratch2.db", allow_raw_sql: true, cache: { ttl_seconds: 0 } });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("now");
    wrapper.unmount();
  });

  it("sends a Postgres connection with a placeholder address", async () => {
    const save = vi.spyOn(treasuryAdminClient, "saveConnection").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="name"]').setValue("pg");
    await wrapper.get('[data-test="type"]').setValue("postgres");
    await wrapper.get('[data-test="dsn"]').setValue("${PG_DSN}");
    await wrapper.get('[data-test="pool"]').setValue("3");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("pg", { type: "postgres", dsn: "${PG_DSN}", max_pool_size: 3 });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next start");
    wrapper.unmount();
  });

  it("shows Treasury's refusal and keeps the form open", async () => {
    vi.spyOn(treasuryAdminClient, "saveConnection").mockRejectedValue(new Error('The dsn must be a placeholder like "${POSTGRES_DSN}"'));
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="name"]').setValue("pg");
    await wrapper.get('[data-test="type"]').setValue("postgres");
    await wrapper.get('[data-test="dsn"]').setValue("postgresql://x");
    await wrapper.get('[data-test="form"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("placeholder");
    expect(wrapper.find('[data-test="form"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("removes a saved connection after confirming", async () => {
    const remove = vi.spyOn(treasuryAdminClient, "removeConnection").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await wrapper.get('[data-test="row-reports"] [data-test="remove"]').trigger("click");
    await flushPromises();
    const confirm = wrapper.findAll("button").find((b) => b.text() === "Remove" && !b.attributes("data-test"));
    await confirm!.trigger("click");
    await flushPromises();
    expect(remove).toHaveBeenCalledWith("reports");
    wrapper.unmount();
  });

  it("saves the cache defaults and puts the built-in ones back", async () => {
    const save = vi.spyOn(treasuryAdminClient, "saveDefaultCache").mockResolvedValue({ ...VIEW, default_cache_stored: true });
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="cache-save"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-test="default-ttl"]').setValue("10");
    await wrapper.get('[data-test="cache-form"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ ttl_seconds: 10, max_entries: 1000, negative_ttl_seconds: 5 });
    await wrapper.get('[data-test="cache-reset"]').trigger("click");
    await flushPromises();
    expect(save).toHaveBeenLastCalledWith(null);
    wrapper.unmount();
  });
});
