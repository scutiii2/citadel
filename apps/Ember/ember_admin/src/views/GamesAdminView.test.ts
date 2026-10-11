import { flushPromises, mount } from "@vue/test-utils";
import { beforeAll, beforeEach, afterEach, expect, it, vi } from "vitest";
import { GamesAdminClient } from "../api/GamesAdminClient";
import GamesAdminView from "./GamesAdminView.vue";
const game = { id: "ascension", name: "Ascension", description: "Collect", icon: "", version: "1", url: "http://localhost:8060", enabled: true };
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close ??= function () { this.removeAttribute("open"); };
});
beforeEach(() => vi.spyOn(GamesAdminClient.prototype, "registry").mockResolvedValue([game]));
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = ""; });
it("lists registered games and refreshes manifest metadata", async () => {
  const refreshed = vi.spyOn(GamesAdminClient.prototype, "refresh").mockResolvedValue({ ...game, version: "2" });
  const w = mount(GamesAdminView); await flushPromises(); expect(w.find("table").text()).toContain("Ascension"); expect(w.text()).toContain("Enabled");
  vi.spyOn(GamesAdminClient.prototype, "registry").mockResolvedValue([{ ...game, version: "2" }]);
  await w.find("button.refresh-game").trigger("click"); await flushPromises(); expect(refreshed).toHaveBeenCalledWith("ascension"); expect(w.text()).toContain("Refreshed Ascension"); w.unmount();
});
it("registers a URL and reports manifest errors inline", async () => {
  const registered = vi.spyOn(GamesAdminClient.prototype, "register").mockRejectedValueOnce(new Error("Manifest id is invalid")).mockResolvedValue(game);
  const w = mount(GamesAdminView); await flushPromises(); await w.find("input[type=url]").setValue(game.url); await w.find("form").trigger("submit"); await flushPromises();
  expect(w.find("[role=alert]").text()).toContain("Manifest id is invalid");
  await w.find("form").trigger("submit"); await flushPromises(); expect(registered).toHaveBeenCalledWith(game.url); expect(w.text()).toContain("Registered Ascension"); w.unmount();
});
it("requires the exact game id before deregistration and keeps grants explained", async () => {
  const removed = vi.spyOn(GamesAdminClient.prototype, "deregister").mockResolvedValue(undefined);
  const w = mount(GamesAdminView, { attachTo: document.body }); await flushPromises(); await w.find("button.deregister-game").trigger("click"); await flushPromises();
  const dialog = document.querySelector("dialog")!; const input = dialog.querySelector("input")!; const confirm = dialog.querySelector<HTMLButtonElement>("button.confirm")!;
  expect(dialog.textContent).toContain("Permission grants are kept"); expect(confirm.disabled).toBe(true);
  input.value = "wrong"; input.dispatchEvent(new Event("input", { bubbles: true })); await flushPromises(); expect(confirm.disabled).toBe(true);
  input.value = "ascension"; input.dispatchEvent(new Event("input", { bubbles: true })); await flushPromises(); expect(confirm.disabled).toBe(false);
  confirm.click(); await flushPromises(); expect(removed).toHaveBeenCalledWith("ascension"); expect(w.text()).toContain("Deregistered Ascension"); w.unmount();
});

it("keeps the post-registration registry when an older initial load finishes later", async () => {
  let finish!: (games: typeof game[]) => void;
  vi.mocked(GamesAdminClient.prototype.registry).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue([game]);
  vi.spyOn(GamesAdminClient.prototype, "register").mockResolvedValue(game);
  const w = mount(GamesAdminView); await w.find("input[type=url]").setValue(game.url);
  await w.find("form").trigger("submit"); await flushPromises();
  expect(w.find("table").text()).toContain("Ascension");
  finish([]); await flushPromises(); expect(w.find("table").text()).toContain("Ascension"); w.unmount();
});
