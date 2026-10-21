import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import BrainConnectionForm from "./BrainConnectionForm.vue";
import { brainsClient } from "../api/BrainsClient";

vi.mock("../api/BrainsClient", () => ({ brainsClient: { connection: vi.fn(), save: vi.fn(), test: vi.fn() } }));
const connection = { id: "personal-id", scope: "personal" as const, label: "My vault", endpoint: "https://vault.lan",
  folder: "Inbox", enabled: true, allow_write: true, credential_configured: true, revision: 2, generation: "g", status: "configured" };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(brainsClient.connection).mockResolvedValue({ ...connection }); });
it("never fills the saved credential and omits an unchanged key", async () => {
  const w = mount(BrainConnectionForm, { props: { scope: "personal" } }); await flushPromises();
  expect((w.get('input[type="password"]').element as HTMLInputElement).value).toBe("");
  await w.get('input[maxlength="80"]').setValue("Renamed");
  vi.mocked(brainsClient.save).mockResolvedValue({ ...connection, label: "Renamed", revision: 3 });
  await w.findAll("button").find(b => b.text() === "Save connection")!.trigger("click"); await flushPromises();
  expect(brainsClient.save).toHaveBeenCalledWith("personal", expect.objectContaining({ label: "Renamed", expected_revision: 2 }));
  expect(vi.mocked(brainsClient.save).mock.calls[0]![1]).not.toHaveProperty("api_key");
});
it("keeps an edited key after a refused save and testing does not save", async () => {
  const w = mount(BrainConnectionForm, { props: { scope: "personal" } }); await flushPromises();
  await w.get('input[type="password"]').setValue("replacement-key");
  vi.mocked(brainsClient.save).mockRejectedValue(new Error("Connection changed"));
  await w.findAll("button").find(b => b.text() === "Save connection")!.trigger("click"); await flushPromises();
  expect(w.get('[role="alert"]').text()).toContain("Connection changed");
  expect((w.get('input[type="password"]').element as HTMLInputElement).value).toBe("replacement-key");
  vi.mocked(brainsClient.test).mockResolvedValue({ message: "Read-only test passed" });
  await w.findAll("button").find(b => b.text() === "Test connection")!.trigger("click"); await flushPromises();
  expect(brainsClient.save).toHaveBeenCalledTimes(1);
  expect(brainsClient.test).toHaveBeenCalledWith("personal", expect.objectContaining({ api_key: "replacement-key" }));
});
