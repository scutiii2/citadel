import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import GeneratorView from "./GeneratorView.vue";

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const mocks = vi.hoisted(() => ({ runTool: vi.fn() }));
vi.mock("../api/McpServerClient", () => ({
  McpServerClient: class {
    runTool = mocks.runTool;
  },
}));

const PASSWORD = { password: "Abc123!xyz", length: 10, entropy_bits: 64, message: "Copy it now." };
const SECRET = { secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x", message: "Add it to an app." };
const CODE = { code: "123456", seconds_remaining: 20, period: 30, message: "Valid for 20 s." };

const ok = (structured: Record<string, unknown>) => ({ text: "", isError: false, structured });

async function show() {
  const w = mount(GeneratorView);
  await flushPromises();
  return w;
}
const tabButton = (w: Awaited<ReturnType<typeof show>>, label: string) =>
  w.findAll("button").find((b) => b.text() === label)!;

async function generate(w: { get(selector: string): { trigger(event: string): Promise<void> } }) {
  await w.get("form").trigger("submit");
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.runTool.mockImplementation(async (name: string) => {
    if (name === "tool_gen_generatePassword") return ok(PASSWORD);
    if (name === "tool_gen_generateTotpSecret") return ok(SECRET);
    if (name === "tool_gen_getTotpCode") return ok(CODE);
    return { text: "unknown tool", isError: true };
  });
});
afterEach(() => vi.useRealTimers());

describe("GeneratorView", () => {
  it("keeps the mobile type picker and generated value when a type change is cancelled", async () => {
    const w = await show();
    await generate(w);
    await tabButton(w, "Reveal").trigger("click");
    await w.get('select[aria-label="Generator type"]').setValue("pin");
    await flushPromises();
    expect(w.get('select[aria-label="Generator type"]').element).toHaveProperty("value", "password");
    await w.get('dialog button.cancel').trigger("click");
    await flushPromises();
    expect(w.get('[data-testid=generated-value]').text()).toBe(PASSWORD.password);
    expect(mocks.runTool).toHaveBeenCalledTimes(1);
    w.unmount();
  });

  it("opens and closes mobile options without losing the result or generating again", async () => {
    const w = await show();
    await generate(w);
    const disclosure = w.get('button[aria-controls="generator-options"]');
    expect(disclosure.attributes('aria-expanded')).toBe('false');
    await disclosure.trigger('click');
    await w.get('input[type=range]').setValue('40');
    await disclosure.trigger('click');
    expect(disclosure.attributes('aria-expanded')).toBe('false');
    expect(w.get('[data-testid=generated-value]').text()).toBe('•'.repeat(PASSWORD.password.length));
    expect(mocks.runTool).toHaveBeenCalledTimes(1);
    await generate(w);
    expect(mocks.runTool).toHaveBeenLastCalledWith('tool_gen_generatePassword', expect.objectContaining({ length: 40 }));
    w.unmount();
  });
  it("makes nothing on open or when a tab is opened, only a hint", async () => {
    const w = await show();

    expect(mocks.runTool).not.toHaveBeenCalled();
    expect(w.find("[data-testid=generated-value]").exists()).toBe(false);
    expect(w.get(".hint").text()).toContain("Press Generate");

    await tabButton(w, "PIN").trigger("click");
    await flushPromises();
    expect(mocks.runTool).not.toHaveBeenCalled();
  });

  it("makes a password when Generate is pressed, hidden until Reveal, with its strength", async () => {
    const w = await show();
    await generate(w);

    expect(mocks.runTool).toHaveBeenCalledWith("tool_gen_generatePassword", expect.objectContaining({ length: 20 }));
    expect(w.get("[data-testid=generated-value]").text()).toBe("•".repeat(10));
    expect(w.get("[role=meter]").attributes("aria-valuenow")).toBe("64");

    await tabButton(w, "Reveal").trigger("click");
    expect(w.get("[data-testid=generated-value]").text()).toBe("Abc123!xyz");
    await tabButton(w, "Hide").trigger("click");
    expect(w.get("[data-testid=generated-value]").text()).not.toContain("Abc");
  });

  it("hides a revealed value again when Regenerate is pressed", async () => {
    const w = await show();
    await generate(w);
    await tabButton(w, "Reveal").trigger("click");
    expect(w.get("[data-testid=generated-value]").text()).toBe("Abc123!xyz");

    await generate(w);
    expect(w.get("[data-testid=generated-value]").text()).toBe("•".repeat(10));
  });

  it("does not make a new value when an option changes, only when Generate is pressed", async () => {
    const w = await show();
    await generate(w);
    mocks.runTool.mockClear();

    await w.get("input[type=checkbox]").setValue(false); // Uppercase
    await flushPromises();
    expect(mocks.runTool).not.toHaveBeenCalled();

    await generate(w);
    expect(mocks.runTool).toHaveBeenCalledWith("tool_gen_generatePassword", expect.objectContaining({ use_upper: false }));
  });

  it("asks for at least one kind of character and does not run without it", async () => {
    const w = await show();

    for (const box of w.findAll("input[type=checkbox]").slice(0, 4)) await box.setValue(false);
    await flushPromises();
    mocks.runTool.mockClear();
    await w.get("form").trigger("submit");

    expect(w.text()).toContain("Choose at least one kind of character.");
    expect(mocks.runTool).not.toHaveBeenCalled();
  });

  it("hides a TOTP secret until Reveal is pressed", async () => {
    const w = await show();

    await tabButton(w, "TOTP secret").trigger("click");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(w.get("[data-testid=generated-value]").text()).not.toContain("JBSWY");

    await tabButton(w, "Reveal").trigger("click");
    expect(w.get("[data-testid=generated-value]").text()).toBe("JBSWY3DPEHPK3PXP");
  });

  it("shows a TOTP code in groups and asks again when it expires", async () => {
    vi.useFakeTimers();
    const w = await show();

    await tabButton(w, "TOTP code").trigger("click");
    const run = w.get("form button.primary");
    expect(run.attributes("disabled")).toBeDefined(); // no secret yet
    await w.get("input[type=password]").setValue("JBSWY3DPEHPK3PXP");
    await w.get("form").trigger("submit");
    await flushPromises();
    expect(w.get("[data-testid=generated-value]").text()).toBe("••••••");
    await tabButton(w, "Reveal").trigger("click");
    expect(w.get("[data-testid=generated-value]").text()).toBe("123 456");

    mocks.runTool.mockClear();
    await vi.advanceTimersByTimeAsync(20_300);
    expect(mocks.runTool).toHaveBeenCalledWith("tool_gen_getTotpCode", expect.objectContaining({ secret: "JBSWY3DPEHPK3PXP" }));
    w.unmount();
  });

  describe("leaving with a generated value", () => {
    const dialogButton = (label: string) =>
      [...document.body.querySelectorAll("dialog button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

    it("switches tabs without a question when nothing was generated", async () => {
      const w = await show();

      await tabButton(w, "PIN").trigger("click");
      await flushPromises();

      expect(w.find("dialog[open]").exists()).toBe(false);
      expect(w.text()).toContain("Digits: 6");
    });

    it("warns before another tab drops the value, and keeps it when cancelled", async () => {
      const w = mount(GeneratorView, { attachTo: document.body });
      await flushPromises();
      await generate(w);

      await tabButton(w, "PIN").trigger("click");
      await flushPromises();
      expect(document.body.querySelector("dialog[open]")?.textContent).toContain("Generated values are not stored");
      dialogButton("Cancel")!.click();
      await flushPromises();

      expect(w.text()).toContain("Length: 20");
      expect(w.find("[data-testid=generated-value]").exists()).toBe(true);
      w.unmount();
    });

    it("removes every generated value once the tab change is confirmed", async () => {
      const w = mount(GeneratorView, { attachTo: document.body });
      await flushPromises();
      await generate(w);

      await tabButton(w, "PIN").trigger("click");
      await flushPromises();
      dialogButton("Discard and leave")!.click();
      await flushPromises();

      expect(w.text()).toContain("Digits: 6");
      expect(w.find("[data-testid=generated-value]").exists()).toBe(false);
      await tabButton(w, "Password").trigger("click");
      await flushPromises();
      expect(w.find("[data-testid=generated-value]").exists()).toBe(false);
      w.unmount();
    });

    it("warns before the page is left, and stays when cancelled", async () => {
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: "/generator", component: GeneratorView },
          { path: "/other", component: { template: "<div />" } },
        ],
      });
      await router.push("/generator");
      const w = mount({ template: "<RouterView />" }, { global: { plugins: [router] }, attachTo: document.body });
      await flushPromises();
      await generate(w);

      void router.push("/other");
      await flushPromises();
      expect(router.currentRoute.value.path).toBe("/generator");
      expect(document.body.querySelector("dialog[open]")?.textContent).toContain("Leaving this page");
      dialogButton("Cancel")!.click();
      await flushPromises();
      expect(router.currentRoute.value.path).toBe("/generator");

      void router.push("/other");
      await flushPromises();
      dialogButton("Discard and leave")!.click();
      await flushPromises();
      expect(router.currentRoute.value.path).toBe("/other");
      w.unmount();
    });
  });

  it("shows the tool's error", async () => {
    mocks.runTool.mockResolvedValue({ text: "Secret is not valid base32.", isError: true });

    const w = await show();
    await generate(w);

    expect(w.get("[role=alert]").text()).toBe("Secret is not valid base32.");
  });

  it("keeps the previous masked result available if regeneration fails", async () => {
    const w = await show();
    await generate(w);
    await tabButton(w, "Reveal").trigger("click");
    mocks.runTool.mockResolvedValue({ text: "Generator unavailable.", isError: true });
    await generate(w);
    expect(w.get('[role=alert]').text()).toBe('Generator unavailable.');
    expect(w.get('[data-testid=generated-value]').text()).toBe('•'.repeat(PASSWORD.password.length));
    await tabButton(w, "Reveal").trigger("click");
    expect(w.get('[data-testid=generated-value]').text()).toBe(PASSWORD.password);
    w.unmount();
  });
});
