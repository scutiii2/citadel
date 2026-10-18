import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ForgeGroup, ForgeWorker } from "../api/ForgeClient";
import ForgeInviteModal from "./ForgeInviteModal.vue";

const worker = (id: number, label: string, extra: Partial<ForgeWorker> = {}): ForgeWorker => ({
  id, provider: "claude", label, reported_plan: "Max", online: true, eligible: true, problem: null, last_seen: null, created_at: "2026-10-18T10:00:00", ...extra,
});
const group: ForgeGroup = {
  id: 1, title: "Build", mode: "ask", relay: false, running: false, created_at: "2026-10-18T10:00:00",
  members: [{ worker_id: 1, label: "claude", provider: "claude", folder: "C:/site", online: true }],
};

const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});

const workers = [worker(1, "claude"), worker(2, "codex", { provider: "codex" }), worker(3, "basic", { eligible: false, problem: "Plan not eligible: Free" })];
const setup = (props: object = {}) =>
  mount(ForgeInviteModal, { props: { open: true, group, workers, busy: false, error: "", ...props }, attachTo: document.body });

describe("ForgeInviteModal", () => {
  it("disables workers that are already in or not eligible, and says why", () => {
    const wrapper = setup();
    const rows = wrapper.findAll("input[type=radio]");

    expect(rows.map((r) => (r.element as HTMLInputElement).disabled)).toEqual([true, false, true]);
    expect(wrapper.text()).toContain("Already in this group");
    expect(wrapper.text()).toContain("Plan not eligible: Free");
  });

  it("suggests the folder the group already uses", () => {
    expect((setup().get("input[type=text]").element as HTMLInputElement).value).toBe("C:/site");
  });

  it("invites the chosen worker with the folder", async () => {
    const wrapper = setup();

    await wrapper.findAll("input[type=radio]")[1]!.setValue(true);
    await wrapper.get("input[type=text]").setValue("  D:/other  ");
    await wrapper.get("form").trigger("submit");

    expect(wrapper.emitted("invite")).toEqual([[2, "D:/other"]]);
  });

  it("needs a worker and a folder", async () => {
    const wrapper = setup();
    expect((wrapper.get("button[type=submit]").element as HTMLButtonElement).disabled).toBe(true);

    await wrapper.findAll("input[type=radio]")[1]!.setValue(true);
    await wrapper.get("input[type=text]").setValue("   ");
    expect((wrapper.get("button[type=submit]").element as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows the server's refusal", () => {
    expect(setup({ error: "Plan not eligible: Pro" }).get("[role=alert]").text()).toContain("Plan not eligible: Pro");
  });

  it("points to pairing when there is no worker at all", () => {
    expect(setup({ workers: [] }).text()).toContain("Add a worker first");
  });
});


describe("ForgeInviteModal folder browsing", () => {
  it("browses on the chosen worker, starting from the typed folder", async () => {
    const browse = vi.fn().mockResolvedValue("D:/picked");
    const wrapper = setup({ browse });
    expect(wrapper.get("button.browse").attributes("disabled")).toBeDefined(); // no worker chosen yet

    await wrapper.findAll("input[type=radio]")[1].setValue(true);
    await wrapper.get("button.browse").trigger("click");
    await flushPromises();

    expect(browse).toHaveBeenCalledWith(2, "C:/site");
    expect((wrapper.get("input[type=text]").element as HTMLInputElement).value).toBe("D:/picked");
  });

  it("cannot browse an offline worker", async () => {
    const wrapper = mount(ForgeInviteModal, {
      props: { open: true, group, workers: [worker(5, "away", { online: false })], busy: false, error: "", browse: vi.fn() },
      attachTo: document.body,
    });

    await wrapper.get("input[type=radio]").setValue(true);

    expect(wrapper.get("button.browse").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("That worker is offline");
  });
});
