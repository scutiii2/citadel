import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import BrainView from "./BrainView.vue";
import { brainClient } from "../api/BrainClient";

const saved = {
  label: "Shared", endpoint: "https://vault.lan", folder: "Inbox", enabled: true,
  allow_write: true, revision: 2, status: "configured", credential_configured: true,
};

afterEach(() => vi.restoreAllMocks());

it("shows key presence without putting any stored key in the form or save request", async () => {
  const fixture = "fixture-should-never-enter-the-view";
  vi.spyOn(brainClient, "connection").mockResolvedValue({ ...saved, ...{ api_key: fixture } });
  const save = vi.spyOn(brainClient, "save")
    .mockRejectedValueOnce(new Error("Connection changed"))
    .mockResolvedValueOnce({ ...saved, label: "Renamed", revision: 3 });
  const wrapper = mount(BrainView);
  await flushPromises();
  const key = wrapper.get<HTMLInputElement>('input[type="password"]');
  expect(key.element.value).toBe("");
  expect(wrapper.text()).toContain("API key configured");
  expect(wrapper.html()).not.toContain(fixture);
  const label = wrapper.get<HTMLInputElement>('input[name="label"]');
  await label.setValue("Renamed");
  expect(save).not.toHaveBeenCalled();
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("Connection changed");
  expect(label.element.value).toBe("Renamed");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="status"]').text()).toContain("Connection saved");
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ label: "Renamed", expected_revision: 2 }));
  expect(save.mock.calls[0]![0]).not.toHaveProperty("api_key");
  expect(key.element.value).toBe("");
  wrapper.unmount();
});

it("distinguishes legacy status and tests unsaved changes without saving", async () => {
  vi.spyOn(brainClient, "connection").mockResolvedValue({ ...saved, status: "legacy", credential_configured: false });
  const test = vi.spyOn(brainClient, "test").mockResolvedValue({ message: "Read-only test passed" });
  const wrapper = mount(BrainView);
  await flushPromises();
  expect(wrapper.text()).toContain("No managed API key");
  await wrapper.get('input[type="url"]').setValue("https://candidate.lan");
  await wrapper.get('input[type="password"]').setValue("candidate-fixture");
  await wrapper.findAll("button").find(button => button.text() === "Test connection")!.trigger("click");
  await flushPromises();
  expect(test).toHaveBeenCalledWith(expect.objectContaining({ endpoint: "https://candidate.lan", api_key: "candidate-fixture" }));
  expect(wrapper.text()).toContain("Read-only test passed");
  wrapper.unmount();
});
