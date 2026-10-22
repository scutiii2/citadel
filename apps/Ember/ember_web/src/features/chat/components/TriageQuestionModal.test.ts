import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
import { triageClient, type TriageForm } from "../api/TriageClient";
import TriageQuestionModal from "./TriageQuestionModal.vue";

vi.mock("../api/TriageClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/TriageClient")>()),
  triageClient: { titles: vi.fn(), ask: vi.fn() },
}));

const titles = vi.mocked(triageClient.titles);

// jsdom has no <dialog> methods.
beforeEach(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
  titles.mockReset();
});

afterEach(() => {
  document.body.innerHTML = "";
});

function mountModal(submit: (form: TriageForm) => Promise<void> = vi.fn().mockResolvedValue(undefined)) {
  return mount(TriageQuestionModal, { props: { open: true, submit }, attachTo: document.body });
}

const input = (wrapper: VueWrapper, label: string) => wrapper.get(`[aria-label="${label}"]`);
const askButton = (wrapper: VueWrapper) => wrapper.findAll("button").find((b) => b.text().startsWith("Ask"))!;
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll("button").find((b) => b.text() === text)!;

async function fillChoice(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("textarea").setValue("SQLite database is locked");
  await wrapper.get('input[type="text"]').setValue("Which area?");
  await input(wrapper, "Option 1 description").setValue("SQL and storage");
  await input(wrapper, "Option 2 description").setValue("Connections");
}

describe("a multiple choice question", () => {
  it("needs titles before it can be asked, and Generate titles fills them in", async () => {
    titles.mockResolvedValue(["database", "network"]);
    const wrapper = mountModal();
    await fillChoice(wrapper);

    expect(askButton(wrapper).attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Generate titles, or type one word for each option.");

    await button(wrapper, "Generate titles").trigger("click");
    await flushPromises();

    expect(titles).toHaveBeenCalledWith(["SQL and storage", "Connections"]);
    expect((input(wrapper, "Option 1 title").element as HTMLInputElement).value).toBe("database");
    expect(askButton(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("sends the form, then closes and empties itself", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountModal(submit);
    await fillChoice(wrapper);
    await input(wrapper, "Option 1 title").setValue("Database");
    await input(wrapper, "Option 2 title").setValue("network");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submit).toHaveBeenCalledExactlyOnceWith({
      kind: "choice",
      text: "SQLite database is locked",
      question: "Which area?",
      options: [
        { title: "database", description: "SQL and storage" },
        { title: "network", description: "Connections" },
      ],
    });
    expect(wrapper.emitted("close")).toHaveLength(1);
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("");
  });

  it("refuses two options with the same title", async () => {
    const wrapper = mountModal();
    await fillChoice(wrapper);
    await input(wrapper, "Option 1 title").setValue("area");
    await input(wrapper, "Option 2 title").setValue("Area");

    expect(askButton(wrapper).attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Each option needs its own one-word title.");
  });

  it("keeps between two and ten options", async () => {
    const wrapper = mountModal();

    expect(wrapper.findAll('[aria-label^="Remove option"]').every((b) => b.attributes("disabled") !== undefined)).toBe(true);
    for (let i = 0; i < 12; i++) await button(wrapper, "Add option").trigger("click");

    expect(wrapper.findAll(".option")).toHaveLength(10);
    expect(button(wrapper, "Add option").attributes("disabled")).toBeDefined();
    await wrapper.get('[aria-label="Remove option 3"]').trigger("click");
    expect(wrapper.findAll(".option")).toHaveLength(9);
  });

  it("shows why titles could not be written and lets the person type them", async () => {
    titles.mockRejectedValue(new ApiError(503, "Option titles are unavailable: the title-writer agent is not running"));
    const wrapper = mountModal();
    await fillChoice(wrapper);

    await button(wrapper, "Generate titles").trigger("click");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain("the title-writer agent is not running");
    expect((button(wrapper, "Generate titles").element as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("a yes or no question", () => {
  it("takes no options and sends none", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountModal(submit);
    await button(wrapper, "Yes or no").trigger("click");
    await wrapper.get("textarea").setValue("It is down");
    await wrapper.get('input[type="text"]').setValue("Is there a problem?");

    expect(wrapper.find(".options").exists()).toBe(false);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submit).toHaveBeenCalledExactlyOnceWith({ kind: "yes_no", text: "It is down", question: "Is there a problem?", options: [] });
  });
});

describe("a score question", () => {
  async function fillScore(wrapper: VueWrapper): Promise<void> {
    await button(wrapper, "Score").trigger("click");
    await wrapper.get("textarea").setValue("It is down");
    await wrapper.get('input[type="text"]').setValue("How urgent?");
  }

  it("starts with three levels, needs every one described, and sends them lowest first", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountModal(submit);
    await fillScore(wrapper);

    expect(wrapper.find('[aria-label="Option 1 title"]').exists()).toBe(false);
    expect(wrapper.findAll(".option")).toHaveLength(3);
    expect(wrapper.find('[aria-label="Level 1 (lowest)"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Level 3 (highest)"]').exists()).toBe(true);
    expect(askButton(wrapper).attributes("disabled")).toBeDefined();

    await input(wrapper, "Level 1 (lowest)").setValue("Can wait");
    await input(wrapper, "Level 2").setValue("Soon");
    await input(wrapper, "Level 3 (highest)").setValue("Right now");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submit).toHaveBeenCalledExactlyOnceWith({
      kind: "score", text: "It is down", question: "How urgent?", options: [], levels: ["Can wait", "Soon", "Right now"],
    });
  });

  it("keeps between two and ten levels", async () => {
    const wrapper = mountModal();
    await button(wrapper, "Score").trigger("click");

    for (let i = 0; i < 12; i++) await button(wrapper, "Add level").trigger("click");
    expect(wrapper.findAll(".option")).toHaveLength(10);
    expect(button(wrapper, "Add level").attributes("disabled")).toBeDefined();

    for (let i = 0; i < 12; i++) await wrapper.get('[aria-label="Remove level 1"]').trigger("click");
    expect(wrapper.findAll(".option")).toHaveLength(2);
  });
});

describe("show details", () => {
  it("is off by default and asks for a trace once ticked, staying ticked for the next question", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const wrapper = mountModal(submit);
    await button(wrapper, "Yes or no").trigger("click");
    await wrapper.get("textarea").setValue("It is down");
    await wrapper.get('input[type="text"]').setValue("Is there a problem?");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(submit.mock.calls[0]![0]).not.toHaveProperty("trace");

    await wrapper.get('input[type="checkbox"]').setValue(true);
    await wrapper.get("textarea").setValue("It is down again");
    await wrapper.get('input[type="text"]').setValue("Is there a problem?");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submit.mock.calls[1]![0]).toMatchObject({ kind: "yes_no", trace: true });
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(true);
  });
});

describe("when the question fails", () => {
  it("stays open with the message and keeps what was typed", async () => {
    const submit = vi.fn().mockRejectedValue(new ApiError(503, "The Triage Assistant is unavailable: the Triage Assistant is not running"));
    const wrapper = mountModal(submit);
    await button(wrapper, "Yes or no").trigger("click");
    await wrapper.get("textarea").setValue("It is down");
    await wrapper.get('input[type="text"]').setValue("Is there a problem?");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role=alert]").text()).toContain("the Triage Assistant is not running");
    expect(wrapper.emitted("close")).toBeUndefined();
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("It is down");
  });
});
