import { mount } from "@vue/test-utils";
import { expect, it, vi } from "vitest";
import GameStage from "./GameStage.vue";
const game = { id: "ascension", name: "Ascension", description: "", icon: "", wallpaper: "", version: "1", url: "http://localhost:8060" };
it.each(["https://foreign.example/#ticket=x", "javascript:alert(1)", "http://user@localhost:8060/#ticket=x"])("refuses a launch URL outside the registered origin: %s", url => {
  const w = mount(GameStage, { props: { game, url } }); expect(w.find("iframe").exists()).toBe(false); expect(w.text()).toContain("Game URL is not allowed"); w.unmount();
});
it("sandboxes the game and accepts only its window, origin and protocol messages", async () => {
  const removed = vi.spyOn(window, "removeEventListener");
  const w = mount(GameStage, { attachTo: document.body, props: { game, url: game.url + "/#ticket=x" } });
  const frame = w.find("iframe"); const source = (frame.element as HTMLIFrameElement).contentWindow;
  expect(source).not.toBeNull();
  // allow-forms: the game's Begin battle is a form submit, which a sandbox without it silently blocks.
  expect(frame.attributes("sandbox")?.split(" ").sort()).toEqual(["allow-forms", "allow-same-origin", "allow-scripts"]); expect(frame.attributes("referrerpolicy")).toBe("no-referrer");
  async function message(origin: string, sender: Window | null, data: unknown) { window.dispatchEvent(new MessageEvent("message", { origin, source: sender, data })); await w.vm.$nextTick(); }
  const ready = { source: "game", type: "ready" };
  await message("https://evil.example", source, ready); await message(game.url, window, ready);
  await message(game.url, source, { source: "other", type: "ready" });
  expect(w.find("[role=status]").exists()).toBe(true);
  expect(source).toBe((w.find("iframe").element as HTMLIFrameElement).contentWindow);
  await message(game.url, source, ready); expect(w.find("[role=status]").exists()).toBe(false);
  await message(game.url, source, { source: "game", type: "resize", height: 100 }); expect(frame.attributes("style")).toContain("320px");
  await message(game.url, source, { source: "game", type: "resize", height: 9000 }); expect(frame.attributes("style")).toContain("4000px");
  await message(game.url, source, { source: "game", type: "resize", height: NaN }); expect(frame.attributes("style")).toContain("4000px");
  await message(game.url, source, { source: "game", type: "close" }); expect(w.emitted("close")).toHaveLength(1);
  w.unmount(); expect(removed).toHaveBeenCalledWith("message", expect.any(Function)); removed.mockRestore();
});
