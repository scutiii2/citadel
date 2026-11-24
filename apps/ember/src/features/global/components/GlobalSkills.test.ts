import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { makeAccount } from "../../../testing/account";
import type { Skill } from "../../skills/api/SkillsClient";
import { globalClient } from "../api/GlobalClient";
import GlobalSkills from "./GlobalSkills.vue";

vi.mock("../api/GlobalClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/GlobalClient")>()),
  globalClient: { skills: vi.fn(), allSkills: vi.fn(), setSkillStatus: vi.fn(), updateSkill: vi.fn(), removeSkill: vi.fn() },
}));
const client = vi.mocked(globalClient);

const skill = (id: number, title: string, status: Skill["status"], extra: Partial<Skill> = {}): Skill => ({
  id, title, when_to_use: `when ${title}`, steps: `steps of ${title}`, tools: "", status, successes: 0, failures: 0,
  created_at: "2026-01-01T00:00:00", failing: false, ...extra,
});

const realShowModal = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
let wrapper: VueWrapper | null = null;

async function mountIt(canWrite: boolean) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().account = makeAccount();
  wrapper = mount(GlobalSkills, { attachTo: document.body, props: { canWrite }, global: { plugins: [pinia] } });
  await flushPromises();
  return wrapper;
}
const button = (w: VueWrapper, text: string) => w.findAll("button").find((b) => b.text() === text)!;

beforeEach(() => {
  vi.clearAllMocks();
  client.skills.mockResolvedValue([skill(1, "Deploy", "active", { steps: "Use <i>care</i>" })]);
  client.allSkills.mockResolvedValue([skill(1, "Deploy", "active"), skill(2, "Backup", "proposed"), skill(3, "Old", "retired")]);
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShowModal;
  HTMLDialogElement.prototype.close = realClose;
  wrapper?.unmount();
  wrapper = null;
});

describe("GlobalSkills", () => {
  it("shows a reader only the active skills, as plain text, with no controls", async () => {
    const w = await mountIt(false);
    expect(client.allSkills).not.toHaveBeenCalled();
    expect(w.text()).toContain("Deploy");
    expect(w.text()).toContain("when Deploy");
    expect(w.find("details pre").text()).toBe("Use <i>care</i>");
    expect(w.find("details pre i").exists()).toBe(false);
    for (const name of ["Approve", "Retire", "Send back for review", "Edit", "Delete"]) {
      expect(w.findAll("button").some((b) => b.text() === name)).toBe(false);
    }
  });

  it("shows a writer the three groups from the full list", async () => {
    const w = await mountIt(true);
    expect(client.skills).not.toHaveBeenCalled();
    const headings = w.findAll("h3").map((h) => h.text());
    expect(headings).toEqual(["Waiting for approval", "Active", "Retired"]);
    expect(w.text()).toContain("Backup");
    expect(w.text()).toContain("Old");
  });

  it("moves a skill between statuses with the right button", async () => {
    const w = await mountIt(true);
    client.setSkillStatus.mockImplementation(async (id, status) => skill(id, id === 2 ? "Backup" : id === 1 ? "Deploy" : "Old", status));
    await button(w, "Approve").trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenLastCalledWith(2, "active");
    await button(w, "Retire").trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenCalledWith(1, "retired");
    await w.get("article[aria-label='Old']").findAll("button").find((b) => b.text() === "Send back for review")!.trigger("click");
    await flushPromises();
    expect(client.setSkillStatus).toHaveBeenCalledWith(3, "proposed");
  });

  it("edits a skill and sends the four fields", async () => {
    client.updateSkill.mockResolvedValue(skill(1, "Deploy", "active", { steps: "new steps" }));
    const w = await mountIt(true);
    await w.get("article[aria-label='Deploy']").findAll("button").find((b) => b.text() === "Edit")!.trigger("click");
    await w.find("textarea[aria-label='Steps']").setValue("new steps");
    await button(w, "Save").trigger("click");
    await flushPromises();
    expect(client.updateSkill).toHaveBeenCalledWith(1, { title: "Deploy", when_to_use: "when Deploy", steps: "new steps", tools: "" });
    expect(w.text()).toContain("new steps");
  });

  it("refuses a field over its limit before sending", async () => {
    const w = await mountIt(true);
    await w.get("article[aria-label='Deploy']").findAll("button").find((b) => b.text() === "Edit")!.trigger("click");
    await w.find("textarea[aria-label='Steps']").setValue("x".repeat(1201));
    expect(button(w, "Save").attributes("disabled")).toBeDefined();
    expect(client.updateSkill).not.toHaveBeenCalled();
  });

  it("deletes only after confirmation", async () => {
    client.removeSkill.mockResolvedValue(undefined);
    const w = await mountIt(true);
    await w.findAll("button").filter((b) => b.text() === "Delete")[0].trigger("click");
    expect(client.removeSkill).not.toHaveBeenCalled();
    await w.findAll("button").filter((b) => b.text() === "Delete").at(-1)!.trigger("click");
    await flushPromises();
    expect(client.removeSkill).toHaveBeenCalledTimes(1);
  });

  it("says in words that a failing skill is not offered", async () => {
    client.allSkills.mockResolvedValue([skill(1, "Flaky", "active", { failing: true, failures: 4 })]);
    const w = await mountIt(true);
    expect(w.text()).toContain("Failing: agents are not offered it. Editing resets the counts.");
  });

  it("shows an error and retries a failed load", async () => {
    client.skills.mockRejectedValueOnce(new ApiError(503, "Storage is unavailable"));
    const w = await mountIt(false);
    expect(w.text()).toContain("Storage is unavailable");
    await button(w, "Try again").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Deploy");
  });

  it("shows the server's reason when an action is refused and keeps the row", async () => {
    client.setSkillStatus.mockRejectedValue(new ApiError(409, "You already have 50 active skills. Retire one first."));
    const w = await mountIt(true);
    await button(w, "Approve").trigger("click");
    await flushPromises();
    expect(w.get("[role='alert']").text()).toContain("You already have 50 active skills. Retire one first.");
    expect(w.text()).toContain("Backup");
  });
});
