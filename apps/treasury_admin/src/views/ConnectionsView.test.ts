import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { treasuryAdminClient, type ConnectionsView } from "../api/TreasuryAdminClient";
import { ConfirmModal } from "@citadel/ui";
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

/** Answers whichever confirmation is open (the drawer's or the page's). */
async function confirm(wrapper: VueWrapper, answer: "confirm" | "cancel" = "confirm") {
  const open = wrapper.findAllComponents(ConfirmModal).find((c) => c.props("open"));
  await open!.get(`button.${answer}`).trigger("click");
  await flushPromises();
}

const openRow = async (wrapper: VueWrapper, name: string) => {
  await wrapper.get(`[data-test="row-${name}"] [data-test="open"]`).trigger("click");
  await flushPromises();
};

describe("ConnectionsView", () => {
  it("lists the connections with where they come from and who uses them", async () => {
    const wrapper = await mounted();
    expect(wrapper.get('[data-test="row-data"]').text()).toContain("built-in");
    expect(wrapper.get('[data-test="row-data"]').text()).toContain("ember");
    expect(wrapper.get('[data-test="row-main"]').text()).toContain("changed");
    expect(wrapper.get('[data-test="row-reports"]').text()).toContain("${REPORTS_DSN}");
    wrapper.unmount();
  });

  it("searches and filters the roster", async () => {
    const wrapper = await mounted();
    await wrapper.get('input[type="search"]').setValue("legion");
    expect(wrapper.findAll("tbody tr").map((r) => r.attributes("data-test"))).toEqual(["row-reports"]);
    await wrapper.get('input[type="search"]').setValue("");
    await wrapper.findAll(".filters button").find((b) => b.text().startsWith("Changed"))!.trigger("click");
    expect(wrapper.findAll("tbody tr").map((r) => r.attributes("data-test"))).toEqual(["row-main"]);
    wrapper.unmount();
  });

  it("adds a SQLite connection after confirming and says it is offered at once", async () => {
    const save = vi.spyOn(treasuryAdminClient, "saveConnection").mockResolvedValue({ ...VIEW, applies: "now" });
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="name"]').setValue("scratch2");
    await wrapper.get('[data-test="path"]').setValue("scratch2.db");
    await wrapper.get('[data-test="raw-sql"]').setValue(true);
    await wrapper.get('[data-test="cache"]').setValue("0");
    await wrapper.get('[data-test="save"]').trigger("click");
    expect(save).not.toHaveBeenCalled();
    await confirm(wrapper);
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
    await wrapper.get('[data-test="save"]').trigger("click");
    await confirm(wrapper);
    expect(save).toHaveBeenCalledWith("pg", { type: "postgres", dsn: "${PG_DSN}", max_pool_size: 3 });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next start");
    wrapper.unmount();
  });

  it("shows Treasury's refusal and keeps the draft in the drawer", async () => {
    vi.spyOn(treasuryAdminClient, "saveConnection").mockRejectedValue(new Error('The dsn must be a placeholder like "${POSTGRES_DSN}"'));
    const wrapper = await mounted();
    await wrapper.get('[data-test="add"]').trigger("click");
    await wrapper.get('[data-test="name"]').setValue("pg");
    await wrapper.get('[data-test="type"]').setValue("postgres");
    await wrapper.get('[data-test="dsn"]').setValue("postgresql://x");
    await wrapper.get('[data-test="save"]').trigger("click");
    await confirm(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toContain("placeholder");
    expect((wrapper.get('[data-test="dsn"]').element as HTMLInputElement).value).toBe("postgresql://x");
    wrapper.unmount();
  });

  it("removes a saved connection after confirming, and offers none for a built-in one", async () => {
    const remove = vi.spyOn(treasuryAdminClient, "removeConnection").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await openRow(wrapper, "data");
    expect(wrapper.find('[data-test="remove"]').exists()).toBe(false);
    wrapper.unmount();
    const second = await mounted();
    await openRow(second, "reports");
    await second.get('[data-test="remove"]').trigger("click");
    await flushPromises();
    await confirm(second);
    expect(remove).toHaveBeenCalledWith("reports");
    second.unmount();
  });

  it("saves the cache defaults through the header icons and puts the built-in ones back", async () => {
    const save = vi.spyOn(treasuryAdminClient, "saveDefaultCache").mockResolvedValue({ ...VIEW, default_cache_stored: true });
    const wrapper = await mounted();
    expect(wrapper.find('.draft-actions [data-test="save"]').exists()).toBe(false);
    await wrapper.get('[data-test="default-ttl"]').setValue("10");
    await wrapper.get('.draft-actions [data-test="save"]').trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledWith({ ttl_seconds: 10, max_entries: 1000, negative_ttl_seconds: 5 });
    await wrapper.get('[data-test="cache-reset"]').trigger("click");
    await flushPromises();
    expect(save).toHaveBeenLastCalledWith(null);
    wrapper.unmount();
  });

  it("keeps a cache draft while search hides its field, and discards it after asking", async () => {
    const wrapper = await mounted();
    await wrapper.get('[data-test="default-ttl"]').setValue("10");
    await wrapper.get('input[aria-label="Search cache defaults"]').setValue("entries");
    expect(wrapper.get('[data-test="default-ttl"]').element.closest(".field")!.getAttribute("style")).toContain("display: none");
    await wrapper.get('.draft-actions [data-test="cancel"]').trigger("click");
    await confirm(wrapper);
    expect((wrapper.get('[data-test="default-ttl"]').element as HTMLInputElement).value).toBe("30");
    wrapper.unmount();
  });
});
