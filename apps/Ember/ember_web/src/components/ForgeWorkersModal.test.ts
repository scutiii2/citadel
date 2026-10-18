import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ForgeCreatedWorker, ForgeWorker } from "../api/ForgeClient";
import ForgeWorkersModal from "./ForgeWorkersModal.vue";

const worker = (id: number, label: string, extra: Partial<ForgeWorker> = {}): ForgeWorker => ({
  id, provider: "claude", label, reported_plan: "Max", online: true, eligible: true, problem: null, last_seen: null, created_at: "2026-10-18T10:00:00", ...extra,
});

const realShow = HTMLDialogElement.prototype.showModal;
const realClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  localStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => {
  HTMLDialogElement.prototype.showModal = realShow;
  HTMLDialogElement.prototype.close = realClose;
});

const setup = (props: object = {}) =>
  mount(ForgeWorkersModal, {
    props: { open: true, workers: [], plans: { claude: [], codex: [] }, canEditPlans: false, busy: false, error: "", created: null, ...props },
    attachTo: document.body,
  });

describe("ForgeWorkersModal", () => {
  it("lists workers with their plan, state and eligibility in text", () => {
    const wrapper = setup({
      workers: [
        worker(1, "claude"),
        worker(2, "codex", { provider: "codex", online: false, reported_plan: null, eligible: false, problem: "Plan not eligible: not reported yet" }),
      ],
    });

    const text = wrapper.text();
    expect(text).toContain("@claude");
    expect(text).toContain("Max");
    expect(text).toContain("Online");
    expect(text).toContain("Eligible");
    expect(text).toContain("Offline");
    expect(text).toContain("plan not reported yet");
    expect(text).toContain("Plan not eligible: not reported yet");
  });

  it("asks to remove a worker", async () => {
    const w = worker(1, "claude");
    const wrapper = setup({ workers: [w] });

    await wrapper.get("button.remove").trigger("click");

    expect(wrapper.emitted("remove")).toEqual([[w]]);
  });

  it("creates a worker; the label follows the provider until it is edited", async () => {
    const wrapper = setup();
    const label = () => (wrapper.get("input[type=text]").element as HTMLInputElement).value;
    expect(label()).toBe("claude");

    await wrapper.findAll("button").find((b) => b.text() === "Codex")!.trigger("click");
    expect(label()).toBe("codex");

    await wrapper.get("input[type=text]").setValue("reviewer");
    await wrapper.findAll("button").find((b) => b.text() === "Claude")!.trigger("click");
    expect(label()).toBe("reviewer");  // an edited label is kept

    await wrapper.get("form.add").trigger("submit");
    expect(wrapper.emitted("create")).toEqual([["claude", "reviewer"]]);
  });

  it("refuses a label that cannot be a handle", async () => {
    const wrapper = setup();

    await wrapper.get("input[type=text]").setValue("two words");

    expect((wrapper.get("form.add button[type=submit]").element as HTMLButtonElement).disabled).toBe(true);
    expect(wrapper.get("form.add").text()).toContain("letters, digits");
  });

  it("shows the pairing command and token once", async () => {
    const created: ForgeCreatedWorker = { ...worker(3, "claude"), token: "ft_abc123" };
    const wrapper = setup({ created });

    expect(wrapper.text()).toContain("shown once");
    expect(wrapper.get("code.command").text()).toBe(`.\\run.bat pair ${window.location.origin} ft_abc123 --provider claude`);

    const pick = (name: string) => wrapper.findAll("button").find((b) => b.text() === name)!.trigger("click");
    await pick("Command Prompt");
    expect(wrapper.get("code.command").text()).toBe(`run.bat pair ${window.location.origin} ft_abc123 --provider claude`);
    await pick("Git Bash");
    expect(wrapper.get("code.command").text()).toBe(`./run.bat pair ${window.location.origin} ft_abc123 --provider claude`);
    expect(localStorage.getItem("ember_web.forgeShell")).toBe("gitbash");

    await wrapper.findAll("button").find((b) => b.text() === "Done")!.trigger("click");
    expect(wrapper.emitted("dismissToken")).toHaveLength(1);
  });

  it("hides the plan editor from people who cannot change it", () => {
    expect(setup().text()).not.toContain("Eligible plans");
  });

  it("lets an administrator edit the eligible plans, with hints from the reported ones", async () => {
    const wrapper = setup({
      canEditPlans: true,
      plans: { claude: ["max", "pro"], codex: [] },
      workers: [worker(1, "claude", { reported_plan: "Max 20x" })],
    });

    expect(wrapper.text()).toContain("Eligible plans");
    expect(wrapper.text()).toContain("Max 20x");  // a hint: what a worker reports
    const input = wrapper.get("input[data-provider=claude]");
    expect((input.element as HTMLInputElement).value).toBe("max, pro");

    await input.setValue("max, pro, max 20x");
    await wrapper.get("form[data-provider=claude]").trigger("submit");

    expect(wrapper.emitted("savePlans")).toEqual([["claude", ["max", "pro", "max 20x"]]]);
  });

  it("shows the error", () => {
    expect(setup({ error: "You already have a worker with that label" }).get("[role=alert]").text()).toContain("already have");
  });
});
