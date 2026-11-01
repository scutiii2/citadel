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
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    await button("Reject").trigger("click");
    await flushPromises();
    await wrapper.get('button[aria-label="Edit skill Skill 2"]').trigger("click");
    await button("Retire").trigger("click");
    await flushPromises();
    await wrapper.get('button[aria-label="Edit skill Skill 3"]').trigger("click");
    const sendBack = button("Send back for review");
    await sendBack.trigger("click");
    await flushPromises();
    expect(client.setStatus.mock.calls).toEqual([[1, "retired"], [2, "retired"], [3, "proposed"]]);
  });

  it("asks before deleting and only then calls the API", async () => {
    await setup([skill(1, "proposed")]);
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
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
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    expect(wrapper.get('form[aria-label="Skill editor"]').text()).toContain("no longer offered this skill");
    expect(wrapper.get('article[aria-label="Skill 2"]').text()).not.toContain("Often fails");
  });

  describe("editing", () => {
    const editor = () => wrapper.get('form[aria-label="Skill editor"]');
    const field = (label: string) => editor().findAll("label").find((l) => l.text().startsWith(label))!.get("input, textarea");

    it("opens the editor filled with the skill and saves the changed text, replacing the row", async () => {
      await setup([skill(1, "active", { failures: 3, failing: true })]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      expect((field("Title").element as HTMLInputElement).value).toBe("Skill 1");
      expect((field("Steps").element as HTMLTextAreaElement).value).toBe("stop it, then start it");

      await field("Title").setValue("Reboot an app");
      await field("Steps").setValue("kill it, then launch it");
      client.update.mockResolvedValue(skill(1, "active", { title: "Reboot an app", steps: "kill it, then launch it" }));
      await editor().trigger("submit");
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
      expect(editor().get("button[type=submit]").attributes("disabled")).toBeDefined();
      await editor().trigger("submit");
      expect(client.update).not.toHaveBeenCalled();
    });

    it("shows the server's reason and keeps the editor open when the save is refused", async () => {
      await setup([skill(1, "proposed")]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      client.update.mockRejectedValue(new Error("Another skill already has that title."));
      await editor().trigger("submit");
      await flushPromises();
      expect(editor().text()).toContain("already has that title");
      expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(true);
    });

    it("cancels without calling the API", async () => {
      await setup([skill(1, "proposed")]);
      await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
      await editor().findAll("button").find((b) => b.text() === "Cancel")!.trigger("click");
      expect(client.update).not.toHaveBeenCalled();
      expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(false);
    });
  });

  it("searches titles and when-to-use text without searching steps", async () => {
    await setup([skill(1, "proposed", { title: "Restart the app" }), skill(2, "active", { when_to_use: "a service is offline" })]);
    await wrapper.get('input[aria-label="Search skills"]').setValue("offline");
    expect(wrapper.findAll("article").map((row) => row.attributes("aria-label"))).toEqual(["Skill 2"]);
    await wrapper.get('input[aria-label="Search skills"]').setValue("stop it");
    expect(wrapper.text()).toContain("No skills match your search.");
    await wrapper.get('input[aria-label="Search skills"]').setValue("restart");
    expect(wrapper.findAll("article").map((row) => row.attributes("aria-label"))).toEqual(["Restart the app"]);
  });

  it("keeps Approve inside the selected row without selecting it on approval", async () => {
    await setup([skill(1, "proposed")]);
    client.setStatus.mockResolvedValue(skill(1, "active"));
    expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(false);
    await button("Approve").trigger("click");
    await flushPromises();
    expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(false);
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    expect(wrapper.get('button[aria-label="Edit skill Skill 1"]').attributes("aria-current")).toBe("true");
    expect(wrapper.get('form[aria-label="Skill editor"]').text()).toContain("Steps");
    expect(client.setStatus).toHaveBeenCalledTimes(1);
  });

  it("protects drafts when switching rows or cancelling the editor", async () => {
    await setup([skill(1, "active"), skill(2, "active")]);
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    await wrapper.get('textarea[aria-label="Title"]').setValue("Unsaved title");
    await wrapper.get('button[aria-label="Edit skill Skill 2"]').trigger("click");
    expect(wrapper.get('dialog[aria-label="Discard your changes?"]').attributes("open")).toBeDefined();
    await wrapper.get('dialog[aria-label="Discard your changes?"] button.cancel').trigger("click");
    expect((wrapper.get('textarea[aria-label="Title"]').element as HTMLTextAreaElement).value).toBe("Unsaved title");
    await button("Cancel").trigger("click");
    await wrapper.get('dialog[aria-label="Discard your changes?"] button.confirm').trigger("click");
    await flushPromises();
    expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(false);
    expect(client.update).not.toHaveBeenCalled();
  });

  it("keeps the editor and confirmation available after a failed deletion", async () => {
    await setup([skill(1, "active")]);
    client.remove.mockRejectedValue(new Error("Skill storage is unavailable"));
    await wrapper.get('button[aria-label="Edit skill Skill 1"]').trigger("click");
    await wrapper.get('button[aria-label="Delete skill Skill 1"]').trigger("click");
    await wrapper.get('dialog[aria-label="Delete this skill?"] button.confirm').trigger("click");
    await flushPromises();
    expect(wrapper.get('dialog[aria-label="Delete this skill?"]').text()).toContain("unavailable");
    expect(wrapper.find('form[aria-label="Skill editor"]').exists()).toBe(true);
    expect(wrapper.find('article[aria-label="Skill 1"]').exists()).toBe(true);
  });

  it("moves keyboard focus into the editor and back to its originating row", async () => {
    await setup([skill(1, "active")]);
    const row = wrapper.get('button[aria-label="Edit skill Skill 1"]');
    (row.element as HTMLButtonElement).focus();
    await row.trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.get('textarea[aria-label="Title"]').element);
    await button("Cancel").trigger("click");
    await flushPromises();
    expect(document.activeElement).toBe(row.element);
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
