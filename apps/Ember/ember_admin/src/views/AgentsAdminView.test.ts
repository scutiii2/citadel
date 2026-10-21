import { createPinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsAdminClient, type AgentFile } from "../api/AgentsAdminClient";
import AgentsAdminView from "./AgentsAdminView.vue";

const EMBER: AgentFile = { id: "ember", label: "Ember", port: 9100, entry: true, orchestrator: true, llm: { provider: "anthropic", gateway: "openrouter" } };
const CALC: AgentFile = {
  id: "calc", label: "Calc", port: 9103, focus: "Maths", temperature: 0.2,
  llm: { provider: "anthropic", gateway: "claude", temperature: 0.1 },
} as AgentFile;
const PROVIDERS = {
  anthropic: [{ id: "claude", label: "Claude", model: "m", tiers: [{ tier: "light", id: "haiku" }, { tier: "standard", id: "sonnet" }, { tier: "heavy", id: "opus" }, { tier: "extreme", id: "fable" }] }, { id: "openrouter", label: "OpenRouter", model: "m", tiers: [] }],
  openai: [{ id: "gpt", label: "GPT", model: "m", tiers: [] }],
  laya: [{ id: "local", label: "Local", model: "m", tiers: [] }],
};

// jsdom has no <dialog> methods.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

beforeEach(() => {
  vi.spyOn(agentsAdminClient, "list").mockResolvedValue([EMBER, CALC]);
  vi.spyOn(agentsAdminClient, "gateways").mockResolvedValue(PROVIDERS);
  vi.spyOn(agentsAdminClient, "live").mockResolvedValue({
    ember: { status: "running", tiers: [{ tier: "light", id: "free-model", use_for: "lookups" }, { tier: "heavy", id: "big-model", use_for: "hard tasks" }] },
    calc: { status: "offline", tiers: [] },
  });
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(AgentsAdminView, { attachTo: document.body, global: { plugins: [createPinia()] } });
  await flushPromises();
  return wrapper;
}

describe("per-agent gateway order", () => {
  function configuredAgent() {
    const agent: AgentFile = { ...CALC, llm: { ...CALC.llm!, model: "claude-custom",
      fallback_gateways: [{ gateway: "openrouter", model: "router-custom" }, "bedrock"] } };
    vi.spyOn(agentsAdminClient, "list").mockResolvedValue([EMBER, agent]);
    vi.spyOn(agentsAdminClient, "gateways").mockResolvedValue({ ...PROVIDERS, anthropic: [
      ...PROVIDERS.anthropic, { id: "bedrock", label: "Bedrock", model: "bedrock-default", tiers: [] },
    ] });
    return agent;
  }

  it("shows an agent's configured primary and backups on its card", async () => {
    configuredAgent();
    const wrapper = await mounted();
    expect(wrapper.find("[data-id=calc]").text()).toContain("claude → openrouter → bedrock");
    expect(wrapper.find("[data-id=ember]").text()).not.toContain("bedrock");
    wrapper.unmount();
  });

  it("promotes a backup and keeps each model override with its gateway", async () => {
    const agent = configuredAgent();
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(agent);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    const rows = wrapper.findAll("[data-test=gateway-row]");
    expect(rows).toHaveLength(3);
    await rows[1]!.find("[data-test=move-up]").trigger("click");
    expect(wrapper.find("[data-test=gateway-row]").text()).toContain("Primary");
    expect(wrapper.find<HTMLSelectElement>("[data-test=gateway]").element.value).toBe("openrouter");
    expect(wrapper.find<HTMLInputElement>("[data-test=model]").element.value).toBe("router-custom");
    expect(update).not.toHaveBeenCalled();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update).toHaveBeenCalledWith("calc", expect.objectContaining({ llm: expect.objectContaining({
      gateway: "openrouter", model: "router-custom", fallback_gateways: [
        { gateway: "claude", model: "claude-custom" }, { gateway: "bedrock" },
      ],
    }) }));
    expect(agent.llm?.gateway).toBe("claude");
    wrapper.unmount();
  });

  it("adds and removes backup rows, excludes used gateways, and keeps a primary", async () => {
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    expect(wrapper.find<HTMLButtonElement>("[data-test=remove-gateway]").element.disabled).toBe(true);
    await wrapper.find("[data-test=add-gateway]").trigger("click");
    expect(wrapper.findAll("[data-test=gateway-row]")).toHaveLength(2);
    const backup = wrapper.find<HTMLSelectElement>("[data-test=backup-gateway]");
    expect(backup.element.value).toBe("openrouter");
    expect(backup.find<HTMLOptionElement>('option[value="claude"]').element.disabled).toBe(true);
    expect(wrapper.find<HTMLButtonElement>("[data-test=add-gateway]").element.disabled).toBe(true);
    await wrapper.findAll("[data-test=gateway-row]")[1]!.find("[data-test=remove-gateway]").trigger("click");
    expect(wrapper.findAll("[data-test=gateway-row]")).toHaveLength(1);
    wrapper.unmount();
  });

  it("reorders by drag without saving until the agent form is submitted", async () => {
    configuredAgent();
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    const rows = wrapper.findAll("[data-test=gateway-row]");
    await rows[2]!.find("[data-test=drag-handle]").trigger("dragstart", { dataTransfer: { setData: vi.fn() } });
    await rows[0]!.trigger("drop");
    expect(wrapper.find<HTMLSelectElement>("[data-test=gateway]").element.value).toBe("bedrock");
    expect(update).not.toHaveBeenCalled();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1].llm).toMatchObject({ gateway: "bedrock", fallback_gateways: [
      { gateway: "claude", model: "claude-custom" }, { gateway: "openrouter", model: "router-custom" },
    ] });
    wrapper.unmount();
  });

  it("discards canceled gateway edits and isolates each agent's draft", async () => {
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=add-gateway]").trigger("click");
    await wrapper.find(".agent-form .actions .cancel").trigger("click");
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    expect(wrapper.findAll("[data-test=gateway-row]")).toHaveLength(1);
    expect(wrapper.find<HTMLSelectElement>("[data-test=gateway]").element.value).toBe("openrouter");
    await wrapper.find(".agent-form .actions .cancel").trigger("click");
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    expect(wrapper.findAll("[data-test=gateway-row]")).toHaveLength(1);
    expect(wrapper.find<HTMLSelectElement>("[data-test=gateway]").element.value).toBe("claude");
    wrapper.unmount();
  });

  it("clears incompatible gateway choices when changing provider and omits fallbacks for Laya", async () => {
    configuredAgent();
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=provider]").setValue("openai");
    expect(wrapper.findAll("[data-test=gateway-row]")).toHaveLength(1);
    expect(wrapper.find<HTMLSelectElement>("[data-test=gateway]").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("[data-test=model]").element.value).toBe("");
    await wrapper.find("[data-test=provider]").setValue("laya");
    expect(wrapper.find("[data-test=add-gateway]").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1].llm.provider).toBe("laya");
    expect(update.mock.calls[0]![1].llm).not.toHaveProperty("fallback_gateways");
    wrapper.unmount();
  });
});

describe("AgentsAdminView", () => {
  it("edits Router policy while keeping its internal role and denied tools", async () => {
    const router: AgentFile = { id: "router", label: "Router", port: 9117, internal_role: "router",
      llm: { provider: "laya", gateway: "local" }, decision: {}, delegable: false,
      plan_tool: false, tools: { deny: ["*"] } };
    vi.mocked(agentsAdminClient.list).mockResolvedValue([EMBER, router]);
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(router);
    const wrapper = await mounted();
    expect(wrapper.find("[data-id=router]").text()).toContain("Internal / Router");
    await wrapper.find("[data-id=router] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=routing-deadline]").setValue("7");
    expect(wrapper.find("[data-test=allow]").exists()).toBe(false);
    expect(wrapper.find("[data-test=preview]").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1]).toMatchObject({ internal_role: "router", delegable: false,
      decision: { deadline_seconds: 7 }, tools: { deny: ["*"] } });
    wrapper.unmount();
  });
  it("lists agents with model, port and live status", async () => {
    const wrapper = await mounted();
    expect(wrapper.findAll("[data-test=agent]")).toHaveLength(2);
    expect(wrapper.find("[data-id=ember]").text()).toContain("openrouter");
    expect(wrapper.find("[data-id=ember]").text()).toContain("9100");
    expect(wrapper.find("[data-id=ember] [aria-label='Model tiers']").text()).toContain("big-model");
    expect(wrapper.find("[data-id=calc] [data-test=status]").text()).toContain("Offline");
  });

  it("still lists agents when the live status is not available", async () => {
    vi.spyOn(agentsAdminClient, "live").mockRejectedValue(new Error("Forbidden"));
    const wrapper = await mounted();
    expect(wrapper.findAll("[data-test=agent]")).toHaveLength(2);
    expect(wrapper.find("[data-test=status]").exists()).toBe(false);
  });

  it("creates an agent from the form with the chosen provider and gateway", async () => {
    const create = vi.spyOn(agentsAdminClient, "create").mockResolvedValue({ id: "docs" });
    const wrapper = await mounted();

    await wrapper.find("[data-test=new]").trigger("click");
    await wrapper.find("[data-test=id]").setValue("docs");
    await wrapper.find("[data-test=label]").setValue("Docs");
    await wrapper.find("[data-test=provider]").setValue("openai");
    await wrapper.find("[data-test=gateway]").setValue("gpt");
    await wrapper.find("[data-test=url]").setValue("http://10.0.0.5:9104/mcp");
    await wrapper.find("[data-test=persona]").setValue("Be brief.");
    await wrapper.find("[data-test=allow]").setValue("docs_*, wiki_*");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(create).toHaveBeenCalledOnce();
    const [id, config] = create.mock.calls[0]!;
    expect(id).toBe("docs");
    expect(config).toMatchObject({
      label: "Docs", port: 9104, url: "http://10.0.0.5:9104/mcp", enabled: true, entry: false,
      llm: { provider: "openai", gateway: "gpt" },
      persona: "Be brief.", tools: { allow: ["docs_*", "wiki_*"], deny: [] },
    });
    expect(wrapper.find("[data-test=notice]").text()).toContain("Created docs");
  });

  it("clears a gateway the new provider does not offer", async () => {
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    const gateway = wrapper.find<HTMLSelectElement>("[data-test=gateway]");
    expect(gateway.element.value).toBe("claude");
    await wrapper.find("[data-test=provider]").setValue("openai");
    expect(gateway.element.value).toBe("");
  });

  it("keeps fields the form does not show when saving an edit", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();

    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    expect(wrapper.find<HTMLInputElement>("[data-test=id]").element.disabled).toBe(true);
    await wrapper.find("[data-test=label]").setValue("Calculator");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    const [id, config] = update.mock.calls[0]!;
    expect(id).toBe("calc");
    expect(config).toMatchObject({ label: "Calculator", port: 9103, temperature: 0.2, llm: { temperature: 0.1, gateway: "claude" } });
    expect(config).not.toHaveProperty("id");
  });

  it("shows the reason when ai_agent refuses a save and keeps the form open", async () => {
    vi.spyOn(agentsAdminClient, "create").mockRejectedValue(new Error("port 9104 is already used by enabled agent 'x'"));
    const wrapper = await mounted();
    await wrapper.find("[data-test=new]").trigger("click");
    await wrapper.find("[data-test=id]").setValue("docs");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.find("[data-test=form-error]").text()).toContain("already used");
    expect(wrapper.find("dialog").attributes("open")).toBeDefined();
  });

  it("rejects a port that is not a number in range before calling the server", async () => {
    const create = vi.spyOn(agentsAdminClient, "create").mockResolvedValue({ id: "docs" });
    const wrapper = await mounted();
    await wrapper.find("[data-test=new]").trigger("click");
    await wrapper.find("[data-test=id]").setValue("docs");
    await wrapper.find("[data-test=port]").setValue("70000");
    await wrapper.find("form").trigger("submit");
    expect(create).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test=form-error]").text()).toContain("Port");
  });

  it("removes an agent only after its id is confirmed, and never offers the entry agent", async () => {
    const remove = vi.spyOn(agentsAdminClient, "remove").mockResolvedValue(undefined);
    const wrapper = await mounted();

    expect(wrapper.find<HTMLButtonElement>("[data-id=ember] [data-test=remove]").element.disabled).toBe(true);
    await wrapper.find("[data-id=calc] [data-test=remove]").trigger("click");
    const confirm = wrapper.findAllComponents({ name: "ConfirmModal" }).find((c) => c.props("title") === "Remove agent")!;
    expect(confirm.props("requireText")).toBe("calc");
    expect(remove).not.toHaveBeenCalled();
    await confirm.vm.$emit("confirm");
    await flushPromises();

    expect(remove).toHaveBeenCalledWith("calc");
    expect(wrapper.find("[data-id=calc]").exists()).toBe(false);
  });

  it("offers Reset to defaults only for an overridden agent, and resets after confirming", async () => {
    vi.spyOn(agentsAdminClient, "list").mockResolvedValue([EMBER, { ...CALC, overridden: true }]);
    const reset = vi.spyOn(agentsAdminClient, "reset").mockResolvedValue(CALC);
    const wrapper = await mounted();

    expect(wrapper.find("[data-id=ember] [data-test=reset]").exists()).toBe(false);
    await wrapper.find("[data-id=calc] [data-test=reset]").trigger("click");
    const confirm = wrapper.findAllComponents({ name: "ConfirmModal" }).find((c) => c.props("title") === "Reset agent")!;
    expect(reset).not.toHaveBeenCalled();
    await confirm.vm.$emit("confirm");
    await flushPromises();

    expect(reset).toHaveBeenCalledWith("calc");
    expect(wrapper.find("[data-test=notice]").text()).toContain("Reset calc");
  });

  it("previews which tiers an agent may use and saves the range", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");

    const allowed = () => wrapper.findAll("[data-test=tier-preview] li:not(.off)").map((li) => li.attributes("data-tier"));
    expect(allowed()).toEqual(["light", "standard", "heavy", "extreme"]);
    await wrapper.find("[data-test=min-tier]").setValue("standard");
    await wrapper.find("[data-test=max-tier]").setValue("standard");
    expect(allowed()).toEqual(["standard"]);
    expect(wrapper.find("[data-tier=standard]").text()).toContain("sonnet");

    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1].llm).toMatchObject({ min_tier: "standard", max_tier: "standard" });
  });

  it("refuses a weakest tier that is stronger than the strongest", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=min-tier]").setValue("heavy");
    await wrapper.find("[data-test=max-tier]").setValue("light");
    await wrapper.find("form").trigger("submit");
    expect(update).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test=form-error]").text()).toContain("weakest");
  });

  it("saves the model settings, identity override and no routing for an orchestrator", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(EMBER);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");

    await wrapper.find("[data-test=identity]").setValue("You are Ember.");
    await wrapper.find("[data-test=temperature]").setValue("0.3");
    await wrapper.find("[data-test=max-tokens]").setValue("2048");
    await wrapper.find("[data-test=max-tool-rounds]").setValue("8");
    await wrapper.find("[data-test=max-effort]").setValue("medium");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    const config = update.mock.calls[0]![1];
    expect(config).toMatchObject({
      identity: "You are Ember.",
      llm: { temperature: 0.3, max_tokens: 2048, max_tool_rounds: 8, max_effort: "medium" },
    });
    expect(config).not.toHaveProperty("routing");
  });

  it("loads and saves per-agent turn limits only after Save", async () => {
    const agent: AgentFile = { ...EMBER, llm: { ...EMBER.llm!, max_turn_tokens: 250000, max_turn_seconds: 600 } };
    vi.mocked(agentsAdminClient.list).mockResolvedValue([agent, CALC]);
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(agent);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    expect(wrapper.find<HTMLInputElement>("[data-test=max-turn-tokens]").element.value).toBe("250000");
    expect(wrapper.find<HTMLInputElement>("[data-test=max-turn-seconds]").element.value).toBe("600");
    expect(wrapper.find("[data-test=unsaved]").exists()).toBe(false);
    await wrapper.find("[data-test=max-turn-tokens]").setValue("500000");
    await wrapper.find("[data-test=max-turn-seconds]").setValue("900.5");
    expect(wrapper.find("[data-test=unsaved]").exists()).toBe(true);
    expect(update).not.toHaveBeenCalled();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update).toHaveBeenCalledWith("ember", expect.objectContaining({
      llm: expect.objectContaining({ max_turn_tokens: 500000, max_turn_seconds: 900.5 }),
    }));
    expect(agent.llm!.max_turn_tokens).toBe(250000);
    wrapper.unmount();
  });

  it("leaves default turn limits unset and explains their scope", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(EMBER);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    expect(wrapper.find<HTMLInputElement>("[data-test=max-turn-tokens]").element.placeholder).toContain("100,000");
    expect(wrapper.find<HTMLInputElement>("[data-test=max-turn-seconds]").element.placeholder).toContain("300");
    expect(wrapper.find("[data-test=run-limits]").text()).toContain("input and output");
    expect(wrapper.find("[data-test=run-limits]").text()).toContain("one response");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1].llm).not.toHaveProperty("max_turn_tokens");
    expect(update.mock.calls[0]![1].llm).not.toHaveProperty("max_turn_seconds");
    wrapper.unmount();
  });

  it("resets each run limit to its inherited default", async () => {
    const agent: AgentFile = { ...EMBER, llm: { ...EMBER.llm!, max_turn_tokens: 250000,
      max_turn_seconds: 600, max_tokens: 4096, max_tool_rounds: 12 } };
    vi.mocked(agentsAdminClient.list).mockResolvedValue([agent, CALC]);
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(agent);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    for (const field of ["max-turn-tokens", "max-turn-seconds", "max-tokens", "max-tool-rounds"]) {
      await wrapper.find(`[data-setting-id="${field}"] button[title="Back to default"]`).trigger("click");
      expect(wrapper.find<HTMLInputElement>(`[data-test=${field}]`).element.value).toBe("");
    }
    expect(update).not.toHaveBeenCalled();
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    for (const key of ["max_turn_tokens", "max_turn_seconds", "max_tokens", "max_tool_rounds"]) {
      expect(update.mock.calls[0]![1].llm).not.toHaveProperty(key);
    }
    wrapper.unmount();
  });

  it.each([
    ["max-turn-tokens", "0"], ["max-turn-tokens", "1.5"], ["max-turn-tokens", "100000001"],
    ["max-turn-seconds", "0"], ["max-turn-seconds", "0.0001"], ["max-turn-seconds", "86401"],
    ["max-turn-seconds", "not a number"],
  ])("rejects invalid %s value %s before saving", async (field, value) => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(EMBER);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    await wrapper.find(`[data-test=${field}]`).setValue(value);
    await wrapper.find("form").trigger("submit");
    expect(update).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test=form-error]").text()).toContain("must be");
    wrapper.unmount();
  });

  it("drops run limits when switching to the local Laya provider", async () => {
    const agent: AgentFile = { ...CALC, llm: { ...CALC.llm!, max_turn_tokens: 250000, max_turn_seconds: 600 } };
    vi.mocked(agentsAdminClient.list).mockResolvedValue([EMBER, agent]);
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(agent);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=max-turn-tokens]").setValue("invalid");
    await wrapper.find("[data-test=provider]").setValue("laya");
    expect(wrapper.find("[data-test=run-limits]").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update).toHaveBeenCalledOnce();
    expect(update.mock.calls[0]![1].llm).not.toHaveProperty("max_turn_tokens");
    expect(update.mock.calls[0]![1].llm).not.toHaveProperty("max_turn_seconds");
    wrapper.unmount();
  });

  it("leaves plan_tool out while the checklist is on and writes false when it is switched off", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(EMBER);
    const wrapper = await mounted();
    await wrapper.find("[data-id=ember] [data-test=edit]").trigger("click");
    expect((wrapper.find("input[data-test=plan-tool]").element as HTMLInputElement).checked).toBe(true);

    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[0]![1]).not.toHaveProperty("plan_tool");

    expect(wrapper.find("[data-test=plan-tool-cost]").text()).toContain("200 input tokens");

    await wrapper.find("input[data-test=plan-tool]").setValue(false);
    expect(wrapper.find("[data-test=plan-tool-cost]").exists()).toBe(false);
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(update.mock.calls[1]![1]).toMatchObject({ plan_tool: false });
  });

  it("refuses a model setting that is out of range before calling the server", async () => {
    const update = vi.spyOn(agentsAdminClient, "update").mockResolvedValue(CALC);
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=temperature]").setValue("5");
    await wrapper.find("form").trigger("submit");
    expect(update).not.toHaveBeenCalled();
    expect(wrapper.find("[data-test=form-error]").text()).toContain("Temperature");
  });

  it("previews the assembled prompt for the draft and shows a refusal", async () => {
    const preview = vi.spyOn(agentsAdminClient, "previewPrompt").mockResolvedValue("Your name is Ember: Calc.");
    const wrapper = await mounted();
    await wrapper.find("[data-id=calc] [data-test=edit]").trigger("click");
    await wrapper.find("[data-test=preview-caveman]").setValue(true);
    await wrapper.find("[data-test=preview]").trigger("click");
    await flushPromises();

    expect(preview).toHaveBeenCalledWith("calc", expect.objectContaining({ port: 9103 }), true);
    expect(wrapper.find("[data-test=preview-text]").text()).toBe("Your name is Ember: Calc.");

    preview.mockRejectedValue(new Error("llm.provider: must be one of"));
    await wrapper.find("[data-test=preview]").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test=preview-error]").text()).toContain("llm.provider");
    expect(wrapper.find("[data-test=preview-text]").exists()).toBe(false);
  });

  it("opens the shared prompts dialog", async () => {
    vi.spyOn(agentsAdminClient, "prompts").mockResolvedValue({ values: {}, defaults: {}, overridden: [] });
    const wrapper = await mounted();
    await wrapper.find("[data-test=shared-prompts]").trigger("click");
    expect(wrapper.findComponent({ name: "SharedPromptsModal" }).props("open")).toBe(true);
  });
});
