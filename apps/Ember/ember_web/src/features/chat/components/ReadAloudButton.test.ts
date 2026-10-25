import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAuthStore } from "../../../stores/auth";
import { bardClient } from "../../../api/files/BardClient";
import ReadAloudButton from "./ReadAloudButton.vue";

vi.mock("../../../api/files/BardClient", () => ({ bardClient: { voices: vi.fn(), speak: vi.fn() } }));
beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "ann", email: "a@example.com", email_verified: true, roles: [], permissions: ["tools.execute", "files.download"] };
  vi.mocked(bardClient.voices).mockResolvedValue({ voices: ["v1", "v2"] });
  vi.mocked(bardClient.speak).mockResolvedValue({ file_id: "abc", voice: "v2", duration_s: 1 });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
});
afterEach(() => { document.body.innerHTML = ""; vi.clearAllMocks(); });

it("asks for a voice on every run and stops on a second click", async () => {
  const wrapper = mount(ReadAloudButton, { props: { text: "**Hello** world." }, attachTo: document.body });
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(bardClient.speak).not.toHaveBeenCalled();
  const choose = () => document.body.querySelector<HTMLButtonElement>('[role="menuitem"][data-id="v2"]')!;
  expect(choose()).not.toBeNull();
  choose().click(); await flushPromises();
  expect(bardClient.speak).toHaveBeenCalledWith("Hello world.", "v2", expect.any(AbortSignal));
  expect(wrapper.get("button").attributes("aria-label")).toBe("Stop reading aloud");
  await wrapper.get("button").trigger("click");
  expect(wrapper.get("button").attributes("aria-label")).toBe("Read aloud");
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(choose()).not.toBeNull();
  expect(bardClient.speak).toHaveBeenCalledTimes(1);
  wrapper.unmount();
});

it("hides without both playback permissions", () => {
  useAuthStore().account!.permissions = ["tools.execute"];
  const wrapper = mount(ReadAloudButton, { props: { text: "hello" } });
  expect(wrapper.find("button").exists()).toBe(false);
  wrapper.unmount();
});

it("shows empty voices and fetch errors without choosing a default", async () => {
  vi.mocked(bardClient.voices).mockResolvedValueOnce({ voices: [] }).mockRejectedValueOnce(new Error("Bard unavailable"));
  const wrapper = mount(ReadAloudButton, { props: { text: "hello" } });
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toMatch(/no.*voices/i);
  await wrapper.get("button").trigger("click"); await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe("Bard unavailable");
  expect(bardClient.speak).not.toHaveBeenCalled();
  wrapper.unmount();
});

it("ignores late voice lists after scope changes", async () => {
  let resolve!: (value: { voices: string[] }) => void;
  vi.mocked(bardClient.voices).mockReturnValue(new Promise((r) => { resolve = r; }));
  const wrapper = mount(ReadAloudButton, { props: { text: "hello", scope: "a" }, attachTo: document.body });
  await wrapper.get("button").trigger("click");
  await wrapper.setProps({ scope: "b" });
  resolve({ voices: ["v1"] }); await flushPromises();
  expect(document.querySelector('[role="menu"]')).toBeNull();
  expect(wrapper.get("button").attributes("aria-busy")).toBe("false");
  wrapper.unmount();
});
