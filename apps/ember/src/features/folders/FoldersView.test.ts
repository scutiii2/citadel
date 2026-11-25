import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { makeAccount } from "../../testing/account";
import { foldersClient } from "./api/FoldersClient";
import FoldersView from "./FoldersView.vue";

vi.mock("./api/FoldersClient", () => ({
  FOLDER_MAX_MINUTES: 60,
  foldersClient: { list: vi.fn(), create: vi.fn(), remove: vi.fn(), removeFile: vi.fn(), downloadUrl: vi.fn() },
}));

const client = vi.mocked(foldersClient);

async function setup() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  client.list.mockResolvedValue([]);
  const wrapper = mount(FoldersView, { attachTo: document.body, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}

afterEach(() => vi.clearAllMocks());

describe("FoldersView", () => {
  it("creates a folder from the name and the chosen length, then reloads the list", async () => {
    client.create.mockResolvedValue({} as never);
    const wrapper = await setup();
    const button = wrapper.get("form.new button[type=submit]");
    expect(button.attributes("disabled")).toBeUndefined();

    await wrapper.get("form.new input").setValue("Trip");
    await wrapper.findAll("button.segment").find((b) => b.text() === "15 min")!.trigger("click");
    await wrapper.get("form.new").trigger("submit");
    await flushPromises();

    expect(client.create).toHaveBeenCalledWith("Trip", 15);
    expect(client.list).toHaveBeenCalledTimes(2);
  });

  it("names an unnamed folder Folder", async () => {
    client.create.mockResolvedValue({} as never);
    const wrapper = await setup();
    await wrapper.get("form.new").trigger("submit");
    await flushPromises();

    expect(client.create).toHaveBeenCalledWith("Folder", 60);
  });

  it("shows the server's reason when creating fails", async () => {
    client.create.mockRejectedValue(new Error("You can have 3 open folders at a time"));
    const wrapper = await setup();
    await wrapper.get("form.new input").setValue("Trip");
    await wrapper.get("form.new").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain("3 open folders");
  });
});
