import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { skillsClient, type Skill } from "./api/SkillsClient";
import SkillsView from "./SkillsView.vue";

vi.mock("./api/SkillsClient", () => ({
  skillsClient: { list: vi.fn(), setStatus: vi.fn(), update: vi.fn(), remove: vi.fn() },
  SKILL_LIMITS: { title: 80, when_to_use: 300, steps: 1200, tools: 200 },
}));
const client = vi.mocked(skillsClient);
const skill = (id: number, status: Skill["status"], extra: Partial<Skill> = {}): Skill => ({
  id, title: `Skill ${id}`, when_to_use: "an app is hung", steps: "stop it, then start it", tools: "tool_srv_stopApp",
  status, successes: 0, failures: 0, created_at: "2026-10-25T00:00:00Z", failing: false, ...extra,
});
let wrapper: VueWrapper;
const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  vi.resetAllMocks();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  wrapper?.unmount();
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});
async function setup(skills: Skill[]) {
  client.list.mockResolvedValue(skills);
  wrapper = mount(SkillsView, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const button = (text: string) => wrapper.findAll("button").find((b) => b.text() === text)!;

describe("SkillsView", () => {
  it("groups skills by status and says nothing is used before approval", async () => {
    await setup([skill(1, "proposed"), skill(2, "active", { successes: 2 }), skill(3, "retired")]);
    expect(wrapper.text()).toContain("Nothing is used until you approve it");
    expect(wrapper.get('section[aria-label="Waiting for approval"]').text()).toContain("Skill 1");
    expect(wrapper.get('section[aria-label="Active"]').text()).toContain("Worked 2×, failed 0×");
    expect(wrapper.get('section[aria-label="Retired"]').text()).toContain("Skill 3");
  });

  it("approves a proposal and moves it to Active", async () => {
    await setup([skill(1, "proposed")]);
    client.setStatus.mockResolvedValue(skill(1, "active"));
    await button("Approve").trigger("click");
    await flushPromises();
    expect(client.setStatus).toHaveBeenCalledWith(1, "active");
    expect(wrapper.get('section[aria-label="Active"]').text()).toContain("Skill 1");
    expect(wrapper.text()).toContain("Skill approved.");
  });

  it("rejects, retires and sends back with the right statuses", async () => {
    await setup([skill(1, "proposed"), skill(2, "active"), skill(3, "retired")]);
    client.setStatus.mockImplementation(async (id, status) => skill(id, status));
    await button("Reject").trigger("click");
    await flushPromises();
    await button("Retire").trigger("click");
    await flushPromises();
    const sendBack = wrapper.get('article[aria-label="Skill 3"]').findAll("button").find((b) => b.text() === "Send back for review")!;
    await sendBack.trigger("click");
    await flushPromises();
    expect(client.setStatus.mock.calls).toEqual([[1, "retired"], [2, "retired"], [3, "proposed"]]);
  });

  it("asks before deleting and only then calls the API", async () => {
    await setup([skill(1, "proposed")]);
    await wrapper.get('button[aria-label="Delete skill Skill 1"]').trigger("click");
    expect(client.remove).not.toHaveBeenCalled();
    await wrapper.get('dialog[aria-label="Delete this skill?"] button.confirm').trigger("click");
    await flushPromises();
    expect(client.remove).toHaveBeenCalledWith(1);
    expect(wrapper.text()).toContain("No skills yet.");
  });

  it("flags a skill the server marks as failing and says Ember no longer gets it", async () => {
    await setup([skill(1, "active", { successes: 1, failures: 3, failing: true }), skill(2, "active", { successes: 5, failures: 3 })]);
    const flagged = wrapper.get('article[aria-label="Skill 1"]').text();
    expect(flagged).toContain("Often fails");
    expect(flagged).toContain("no longer offered this skill");
    expect(wrapper.get('article[aria-label="Skill 2"]').text()).not.toContain("Often fails");
  });

  describe("editing", () => {
    const dialog = () => wrapper.get('dialog[aria-label="Edit skill"]');
    const field = (label: string) => dialog().findAll("label").find((l) => l.text().startsWith(label))!.get("input, textarea");

    it("opens the dialog filled with the skill and saves the changed text, replacing the card", async () => {
      await setup([skill(1, "active", { failures: 3, failing: true })]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      expect((field("Title").element as HTMLInputElement).value).toBe("Skill 1");
      expect((field("Steps").element as HTMLTextAreaElement).value).toBe("stop it, then start it");

      await field("Title").setValue("Reboot an app");
      await field("Steps").setValue("kill it, then launch it");
      client.update.mockResolvedValue(skill(1, "active", { title: "Reboot an app", steps: "kill it, then launch it" }));
      await dialog().get("form").trigger("submit");
      await flushPromises();

      expect(client.update).toHaveBeenCalledWith(1, {
        title: "Reboot an app", when_to_use: "an app is hung", steps: "kill it, then launch it", tools: "tool_srv_stopApp",
      });
      const card = wrapper.get('article[aria-label="Reboot an app"]').text();
      expect(card).not.toContain("Often fails");
      expect(wrapper.text()).toContain("counts started over");
    });

    it("will not save an empty required field", async () => {
      await setup([skill(1, "proposed")]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      await field("Steps").setValue("   ");
      expect(dialog().get("button[type=submit]").attributes("disabled")).toBeDefined();
      await dialog().get("form").trigger("submit");
      expect(client.update).not.toHaveBeenCalled();
    });

    it("shows the server's reason and keeps the dialog open when the save is refused", async () => {
      await setup([skill(1, "proposed")]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      client.update.mockRejectedValue(new Error("Another skill already has that title."));
      await dialog().get("form").trigger("submit");
      await flushPromises();
      expect(dialog().text()).toContain("already has that title");
      expect(dialog().attributes("open")).toBeDefined();
    });

    it("cancels without calling the API", async () => {
      await setup([skill(1, "proposed")]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      await dialog().findAll("button").find((b) => b.text() === "Cancel")!.trigger("click");
      expect(client.update).not.toHaveBeenCalled();
      expect(dialog().attributes("open")).toBeUndefined();
    });
  });

  it("shows an error and keeps the skill where it was when the update fails", async () => {
    await setup([skill(1, "proposed")]);
    client.setStatus.mockRejectedValue(new Error("Skill storage is unavailable"));
    await button("Approve").trigger("click");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("unavailable");
    expect(wrapper.get('section[aria-label="Waiting for approval"]').text()).toContain("Skill 1");
  });

  it("offers a retry when the list cannot load", async () => {
    client.list.mockRejectedValueOnce(new Error("offline"));
    wrapper = mount(SkillsView, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.text()).toContain("Could not load skills");
    client.list.mockResolvedValue([skill(1, "proposed")]);
    await button("Try again").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Skill 1");
  });
});
