import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { configIssuesClient, type ConfigIssue } from "../api/ConfigIssuesClient";
import { useAuthStore } from "../stores/auth";
import { useConfigIssuesStore } from "../stores/configIssues";
import ConfigIssuesView from "./ConfigIssuesView.vue";

const ISSUES: ConfigIssue[] = [
  { file: "config_app.json", key: "session_hours", severity: "warning", message: "Very long session" },
  { file: "secrets.json", key: "smtp_password", severity: "error", message: "Missing value" },
  { file: "config_app.json", key: "backup.keep", severity: "error", message: "Must be positive" },
];

async function show(list: () => Promise<ConfigIssue[]> = async () => ISSUES) {
  const pinia = createPinia();
  setActivePinia(pinia);
  vi.spyOn(configIssuesClient, "list").mockImplementation(list);
  useAuthStore().account = { id: 1, username: "ada", email: "a@b.c", email_verified: true, roles: [], permissions: ["config.issues.view"] };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: { template: "<div />" } }, { path: "/config-issues", component: ConfigIssuesView }] });
  await router.push("/config-issues");
  const wrapper = mount(ConfigIssuesView, { global: { plugins: [pinia, router] } });
  await flushPromises();
  return { wrapper, router, store: useConfigIssuesStore() };
}

beforeEach(() => vi.restoreAllMocks());

it("groups issues by file and counts the filters", async () => {
  const { wrapper } = await show();
  expect(wrapper.findAll(".file").map((f) => f.get("code").text())).toEqual(["config_app.json", "secrets.json"]);
  expect(wrapper.findAll(".filters button").map((b) => b.text())).toEqual(["All 3", "Errors 2", "Warnings 1", "Ignored 0"]);
});

it("combines search over file, key and message with the severity filter", async () => {
  const { wrapper } = await show();
  await wrapper.get('input[type="search"]').setValue("config_app");
  expect(wrapper.findAll(".row")).toHaveLength(2);
  await wrapper.findAll(".filters button")[1]!.trigger("click");
  expect(wrapper.findAll(".row").map((r) => r.text())).toEqual([expect.stringContaining("backup.keep")]);
  await wrapper.get('input[type="search"]').setValue("session");
  expect(wrapper.text()).toContain("No issues match these filters.");
  await wrapper.get('input[type="search"]').setValue("");
  await wrapper.findAll(".filters button")[0]!.trigger("click");
  await wrapper.get('input[type="search"]').setValue("positive");
  expect(wrapper.findAll(".row")).toHaveLength(1);
});

it("keeps the error state when a check fails, and does not leave the page", async () => {
  let fail = false;
  const { wrapper, router, store } = await show(async () => { if (fail) throw new Error("Portcullis unreachable"); return ISSUES; });
  fail = true;
  await wrapper.get('[data-test="check"]').trigger("click");
  await flushPromises();
  expect(store.error).toContain("unreachable");
  expect(wrapper.get('[data-test="check-error"]').text()).toContain("The check failed");
  expect(wrapper.findAll(".row")).toHaveLength(3);
  expect(router.currentRoute.value.path).toBe("/config-issues");
});

it("returns home after a successful check that finds nothing", async () => {
  let issues = ISSUES;
  const { wrapper, router } = await show(async () => issues);
  issues = [];
  await wrapper.get('[data-test="check"]').trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/");
});

it("ignores a warning on this browser, drops it from the counts and restores it", async () => {
  localStorage.clear();
  const { wrapper, store } = await show();
  expect(wrapper.findAll('[data-test="ignore"]')).toHaveLength(1);
  await wrapper.get('[data-test="ignore"]').trigger("click");
  expect(store.active).toHaveLength(2);
  expect(wrapper.findAll(".filters button").map((b) => b.text())).toEqual(["All 2", "Errors 2", "Warnings 0", "Ignored 1"]);
  expect(JSON.parse(localStorage.getItem("ember_admin.ignoredIssues.1")!)).toHaveLength(1);
  await wrapper.findAll(".filters button")[3]!.trigger("click");
  expect(wrapper.findAll(".row")).toHaveLength(1);
  await wrapper.get('[data-test="restore"]').trigger("click");
  expect(store.active).toHaveLength(3);
  expect(wrapper.findAll(".filters button")[0]!.text()).toBe("All 3");
});

it("links an issue to the page that fixes it only when it can be fixed there", async () => {
  const { wrapper } = await show(async () => [...ISSUES, { file: "Stronghold Tool services", key: "bard", severity: "error", message: "Configure Bard." }]);
  const rows = wrapper.findAll(".row");
  const fix = (key: string) => rows.find((r) => r.text().includes(key))!.find('[data-test="fix"]');
  expect(fix("backup.keep").exists()).toBe(false); // needs settings.manage, which this account lacks
  expect(fix("smtp_password").exists()).toBe(false);
  expect(fix("bard").attributes("href")).toContain(":26504");
});
