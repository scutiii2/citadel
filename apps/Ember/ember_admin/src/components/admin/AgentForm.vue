<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { AgentConfig, AgentFile, ProviderCatalog } from "../../api/AgentsAdminClient";
import BaseModal from "../BaseModal.vue";
import ToggleSwitch from "../ToggleSwitch.vue";
import SettingRow from "../SettingRow.vue";
import AgentGatewayList, { type GatewayRow } from "./AgentGatewayList.vue";
import RouterPolicyForm from "./RouterPolicyForm.vue";
import ToolScopePicker from "./ToolScopePicker.vue";
import type { CapabilityInfo } from "../../api/CommandsClient";
import { routerPolicyDefaults, validateRouterPolicy } from "../../utils/routerPolicy";

/** Create or edit one agent file. The parent keeps `open`, saves on `save`
 * and closes on `close`; `preview` asks the parent for the assembled system
 * prompt of the draft. Fields the form does not show are carried over from
 * `initial` unchanged. */
const props = defineProps<{
  open: boolean;
  initial: AgentFile | null;
  providers: ProviderCatalog;
  capabilities: CapabilityInfo[];
  suggestedPort: number;
  busy: boolean;
  error: string;
  previewText: string;
  previewing: boolean;
  previewError: string;
}>();
const emit = defineEmits<{ save: [id: string, config: AgentConfig]; preview: [id: string, config: AgentConfig, caveman: boolean]; close: [] }>();

const EFFORTS = ["off", "low", "medium", "high"];
const TIERS = ["light", "standard", "heavy", "extreme"];

const editing = computed(() => props.initial !== null);
const isRouter = computed(() => props.initial?.internal_role === "router");
const decision = ref(routerPolicyDefaults());
const id = ref("");
const label = ref("");
const port = ref("");
const url = ref("");
const enabled = ref(true);
const entry = ref(false);
const orchestrator = ref(false);
const planTool = ref(true);
const provider = ref("anthropic");
const gatewayRows = ref<GatewayRow[]>([{ key: 0, gateway: "", model: "" }]);
const gateway = computed({
  get: () => gatewayRows.value[0]?.gateway ?? "",
  set: (value: string) => { if (gatewayRows.value[0]) gatewayRows.value[0].gateway = value; },
});
const model = computed({
  get: () => gatewayRows.value[0]?.model ?? "",
  set: (value: string) => { if (gatewayRows.value[0]) gatewayRows.value[0].model = value; },
});
const effort = ref("off");
const minTier = ref("");
const maxTier = ref("");
const identity = ref("");
const temperature = ref("");
const maxTokens = ref("");
const maxToolRounds = ref("");
const maxTurnTokens = ref("");
const maxTurnSeconds = ref("");
const maxEffort = ref("");
const previewCaveman = ref(false);
const persona = ref("");
const instructions = ref("");
const focus = ref("");
const allow = ref("");
const deny = ref("");
const localError = ref("");

const isLaya = computed(() => provider.value === "laya");
const gateways = computed(() => props.providers[provider.value] ?? []);
// What a provider uses when the agent names no gateway (ai_agent: agent_spec._DEFAULT_GATEWAY).
const DEFAULT_GATEWAY: Record<string, string> = { anthropic: "claude", openai: "gpt", laya: "local" };
/** The model each tier resolves to on the chosen gateway, and whether the range allows it. */
const tierPreview = computed(() => {
  const gatewayId = gateway.value || DEFAULT_GATEWAY[provider.value];
  const offered = gateways.value.find((g) => g.id === gatewayId)?.tiers ?? [];
  const low = minTier.value ? TIERS.indexOf(minTier.value) : 0;
  const high = maxTier.value ? TIERS.indexOf(maxTier.value) : TIERS.length - 1;
  return TIERS.map((tier, index) => ({
    tier,
    model: offered.find((t) => t.tier === tier)?.id ?? "",
    allowed: index >= low && index <= high,
  })).filter((row) => row.model);
});
const providerIds = computed(() => Object.keys(props.providers));

function joined(globs: string[] | undefined): string {
  return (globs ?? []).join(", ");
}

const initialDraft = ref("");
function draftSignature(): string {
  return JSON.stringify([
    id.value, label.value, port.value, url.value, enabled.value, entry.value,
    orchestrator.value, planTool.value, provider.value,
    gatewayRows.value.map(({ gateway, model }) => [gateway, model]),
    effort.value, minTier.value, maxTier.value, identity.value, temperature.value,
    maxTokens.value, maxToolRounds.value, maxTurnTokens.value, maxTurnSeconds.value, maxEffort.value, persona.value,
    instructions.value, focus.value, allow.value, deny.value,
    decision.value,
  ]);
}
const modified = computed(() => initialDraft.value !== draftSignature());

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    const a = props.initial;
    decision.value = routerPolicyDefaults(a?.decision);
    localError.value = "";
    id.value = a?.id ?? "";
    label.value = a?.label ?? "";
    port.value = String(a?.port ?? props.suggestedPort);
    url.value = a?.url ?? "";
    enabled.value = a?.enabled ?? true;
    entry.value = a?.entry ?? false;
    orchestrator.value = a?.orchestrator ?? false;
    planTool.value = a?.plan_tool !== false;
    provider.value = a?.llm?.provider ?? providerIds.value[0] ?? "anthropic";
    gatewayRows.value = [
      { key: 0, gateway: a?.llm?.gateway ?? "", model: a?.llm?.model ?? "" },
      ...(a?.llm?.fallback_gateways ?? []).map((choice, index) => ({
        key: index + 1,
        gateway: typeof choice === "string" ? choice : choice.gateway,
        model: typeof choice === "string" ? "" : choice.model ?? "",
      })),
    ];
    effort.value = a?.llm?.reasoning_effort ?? "off";
    minTier.value = a?.llm?.min_tier ?? "";
    maxTier.value = a?.llm?.max_tier ?? "";
    identity.value = a?.identity ?? "";
    temperature.value = a?.llm?.temperature === undefined ? "" : String(a.llm.temperature);
    maxTokens.value = a?.llm?.max_tokens === undefined ? "" : String(a.llm.max_tokens);
    maxToolRounds.value = a?.llm?.max_tool_rounds === undefined ? "" : String(a.llm.max_tool_rounds);
    maxTurnTokens.value = a?.llm?.max_turn_tokens === undefined ? "" : String(a.llm.max_turn_tokens);
    maxTurnSeconds.value = a?.llm?.max_turn_seconds === undefined ? "" : String(a.llm.max_turn_seconds);
    maxEffort.value = a?.llm?.max_effort ?? "";
    previewCaveman.value = false;
    persona.value = a?.persona ?? "";
    instructions.value = a?.instructions ?? "";
    focus.value = a?.focus ?? "";
    allow.value = joined(a?.tools?.allow);
    deny.value = joined(a?.tools?.deny);
    initialDraft.value = draftSignature();
  },
  { immediate: true },
);

// Synchronous so loading another agent can set its provider before hydrating
// that agent's own rows, without a queued watcher clearing the new draft.
watch(provider, () => {
  gatewayRows.value = [{ key: 0, gateway: "", model: "" }];
  if (isLaya.value) {
    entry.value = false;
    orchestrator.value = false;
  }
}, { flush: "sync" });

function globs(text: string): string[] {
  return text.split(/[,\n]/).map((g) => g.trim()).filter(Boolean);
}

/** A blank box is "not set" (undefined); text that is not a number in range is null, with the reason in localError. */
function optionalNumber(text: string, name: string, low: number, high: number, whole: boolean): number | undefined | null {
  if (!text.trim()) return undefined;
  const value = Number(text);
  if (!Number.isFinite(value) || value < low || value > high || (whole && !Number.isInteger(value))) {
    localError.value = `${name} must be ${whole ? "a whole number" : "a number"} from ${low} to ${high}.`;
    return null;
  }
  return value;
}

/** The agent file the form describes, or null (with localError set) when a field is invalid. */
function buildConfig(): AgentConfig | null {
  localError.value = "";
  if (isRouter.value && (localError.value = validateRouterPolicy(decision.value))) return null;
  const portNumber = Number(port.value);
  if (!Number.isInteger(portNumber) || portNumber < 1 || portNumber > 65535) {
    localError.value = "Port must be a whole number from 1 to 65535.";
    return null;
  }
  if (minTier.value && maxTier.value && TIERS.indexOf(minTier.value) > TIERS.indexOf(maxTier.value)) {
    localError.value = "The weakest tier cannot be stronger than the strongest tier.";
    return null;
  }
  if (!isLaya.value) {
    const names = gatewayRows.value.map((row) => row.gateway || DEFAULT_GATEWAY[provider.value]);
    if (!names.length || names.some((name) => !gateways.value.some((g) => g.id === name))) {
      localError.value = "Choose at least one available gateway for this provider.";
      return null;
    }
    if (new Set(names).size !== names.length) {
      localError.value = "Each gateway can appear only once.";
      return null;
    }
  }
  const { id: _id, error: _error, overridden: _overridden, ...kept } = props.initial ?? { id: "" };
  const llm: AgentConfig["llm"] = { ...(kept.llm ?? {}), provider: provider.value };
  const setOrDrop = (key: string, value: string): void => {
    if (value) llm[key] = value;
    else delete llm[key];
  };
  setOrDrop("gateway", gateway.value);
  setOrDrop("model", model.value.trim());
  const backups = gatewayRows.value.slice(1).map((row) => ({
    gateway: row.gateway || DEFAULT_GATEWAY[provider.value]!,
    ...(row.model.trim() ? { model: row.model.trim() } : {}),
  }));
  if (!isLaya.value && backups.length) llm.fallback_gateways = backups;
  else delete llm.fallback_gateways;
  const numbers = isLaya.value ? {} : {
    temperature: optionalNumber(temperature.value, "Temperature", 0, 2, false),
    max_tokens: optionalNumber(maxTokens.value, "Output tokens per model call", 1, 1_000_000, true),
    max_tool_rounds: optionalNumber(maxToolRounds.value, "Model/tool rounds", 1, 100, true),
    max_turn_tokens: optionalNumber(maxTurnTokens.value, "Total tokens per turn", 1, 100_000_000, true),
    max_turn_seconds: optionalNumber(maxTurnSeconds.value, "Time per turn", 0.001, 86_400, false),
  };
  if (Object.values(numbers).includes(null as never)) return null;
  if (isLaya.value) {
    // Laya triage runs locally and takes no generation or tier settings.
    for (const key of ["reasoning_effort", "max_tier", "min_tier", "max_effort", "temperature", "max_tokens", "max_tool_rounds", "max_turn_tokens", "max_turn_seconds"]) delete llm[key];
  } else {
    setOrDrop("reasoning_effort", effort.value === "off" ? "" : effort.value);
    setOrDrop("min_tier", minTier.value);
    setOrDrop("max_tier", maxTier.value);
    setOrDrop("max_effort", maxEffort.value);
    for (const [key, value] of Object.entries(numbers)) {
      if (value === undefined) delete llm[key];
      else llm[key] = value;
    }
  }
  const config: AgentConfig = {
    ...kept,
    label: label.value.trim(),
    port: portNumber,
    url: url.value.trim(),
    enabled: enabled.value,
    entry: entry.value,
    orchestrator: orchestrator.value,
    llm,
    identity: identity.value,
    persona: persona.value,
    instructions: instructions.value,
    focus: focus.value,
    tools: { allow: globs(allow.value), deny: globs(deny.value) },
  };
  // On is the default: leave the key out so existing agent files stay as they are.
  if (planTool.value) delete config.plan_tool;
  else config.plan_tool = false;
  if (isRouter.value) {
    config.internal_role = "router";
    config.decision = decision.value;
    config.entry = false;
    config.orchestrator = false;
    config.delegable = false;
    config.memory_recall = false;
    config.plan_tool = false;
    config.tools = { allow: [], deny: ["*"] };
    config.llm = { provider: "laya", gateway: "local", model: "convaiinnovations/laya" };
  }
  delete config.routing; // ai_agent rejects the retired routing option, also in files saved earlier
  for (const key of ["label", "url", "identity", "persona", "instructions", "focus"]) if (!config[key]) delete config[key];
  return config;
}

function submit(): void {
  if (props.busy) return;
  const config = buildConfig();
  if (config) emit("save", id.value.trim(), config);
}

function previewPrompt(): void {
  const config = buildConfig();
  if (config) emit("preview", id.value.trim() || "draft", config, previewCaveman.value);
}
</script>

<template>
  <BaseModal :open="open" :title="editing ? `Edit ${initial?.label || initial?.id}` : 'New agent'" @close="emit('close')">
    <form class="agent-form" @submit.prevent="submit">
      <label class="field">
        <span>Id</span>
        <input v-model="id" data-test="id" type="text" required maxlength="63" pattern="[a-z0-9][a-z0-9\-]*" autocomplete="off" :disabled="editing" placeholder="data-analyst" />
        <small>Lowercase letters, digits and dashes. It names the file and cannot change later.</small>
      </label>
      <div class="row">
        <label class="field grow"><span>Name</span><input v-model="label" data-test="label" type="text" maxlength="80" autocomplete="off" placeholder="Data analyst" /></label>
        <label class="field port"><span>Port</span><input v-model="port" data-test="port" type="number" min="1" max="65535" required /></label>
      </div>

      <label class="field">
        <span>URL</span>
        <input v-model="url" data-test="url" type="text" autocomplete="off" placeholder="http://127.0.0.1:9104/mcp" />
        <small>Where ember and the other agents reach this agent. Leave empty to use this machine and the port above; set it for an agent behind another host or a proxy.</small>
      </label>

      <fieldset>
        <legend>Model</legend>
        <div class="row">
          <label class="field grow"><span>Provider</span>
            <select v-model="provider" :disabled="isRouter" data-test="provider"><option v-for="p in providerIds" :key="p" :value="p">{{ p }}</option></select>
          </label>
        </div>
        <AgentGatewayList v-if="!isLaya" v-model="gatewayRows" :gateways="gateways" :default-gateway="DEFAULT_GATEWAY[provider] ?? ''" :busy="busy" />
        <template v-else>
          <label class="field"><span>Gateway</span><select v-model="gateway" data-test="gateway" disabled><option value="">Local</option><option value="local">Local</option></select></label>
          <label class="field"><span>Model</span><input v-model="model" data-test="model" type="text" disabled placeholder="convaiinnovations/laya" /></label>
        </template>
        <div v-if="!isLaya" class="row">
          <label class="field grow"><span>Reasoning effort</span>
            <select v-model="effort" data-test="effort"><option v-for="e in EFFORTS" :key="e" :value="e">{{ e }}</option></select>
          </label>
          <label class="field grow"><span>Weakest tier it may use</span>
            <select v-model="minTier" data-test="min-tier"><option value="">No limit</option><option v-for="t in TIERS" :key="t" :value="t">{{ t }}</option></select>
          </label>
          <label class="field grow"><span>Strongest tier it may use</span>
            <select v-model="maxTier" data-test="max-tier"><option value="">No limit</option><option v-for="t in TIERS" :key="t" :value="t">{{ t }}</option></select>
          </label>
        </div>
        <ul v-if="tierPreview.length" class="tier-preview" aria-label="Model tiers on this gateway" data-test="tier-preview">
          <li v-for="row in tierPreview" :key="row.tier" :class="{ off: !row.allowed }" :data-tier="row.tier">
            <span>{{ row.tier }}</span><code>{{ row.model }}</code><span class="where">{{ row.allowed ? "available" : "not available" }}</span>
          </li>
        </ul>
        <div v-if="!isLaya" class="row">
          <label class="field grow"><span>Temperature</span><input v-model="temperature" data-test="temperature" type="text" inputmode="decimal" autocomplete="off" placeholder="Model default" /></label>
        </div>
        <label v-if="!isLaya" class="field"><span>Highest effort a delegating agent may request</span>
          <select v-model="maxEffort" data-test="max-effort"><option value="">No limit</option><option v-for="e in EFFORTS" :key="e" :value="e">{{ e }}</option></select>
        </label>
        <small v-if="!isLaya">The orchestrator picks the lightest tier in this range that fits each task. Tier models are set per gateway in ai_agent's gateways directory.</small>
      </fieldset>

      <fieldset v-if="!isLaya" :disabled="busy" :aria-busy="busy" data-test="run-limits">
        <legend>Run limits</legend>
        <p class="hint">Limits apply to each turn this agent runs. Leave a field blank to use its default. Changes apply after Save.</p>
        <SettingRow setting-id="max-turn-tokens" label="Total tokens per turn"
          description="Counts input and output across this agent's model calls, including repeated history. Checked after each response, so usage can exceed the budget by one response."
          :modified="!!maxTurnTokens.trim()" @reset="maxTurnTokens = ''">
          <input v-model="maxTurnTokens" class="limit-input" aria-label="Total tokens per turn" data-test="max-turn-tokens" type="text" inputmode="numeric" autocomplete="off" placeholder="Default: 100,000" />
        </SettingRow>
        <SettingRow setting-id="max-turn-seconds" label="Time per turn (seconds)"
          description="Time budget for this agent's model and tool loop. An external tool already running may finish after the turn stops."
          :modified="!!maxTurnSeconds.trim()" @reset="maxTurnSeconds = ''">
          <input v-model="maxTurnSeconds" class="limit-input" aria-label="Time per turn (seconds)" data-test="max-turn-seconds" type="text" inputmode="decimal" autocomplete="off" placeholder="Default: 300" />
        </SettingRow>
        <SettingRow setting-id="max-tokens" label="Output tokens per model call"
          description="Maximum output for a single response, including thinking where the model counts it. Blank uses the gateway's configured limit."
          :modified="!!maxTokens.trim()" @reset="maxTokens = ''">
          <input v-model="maxTokens" class="limit-input" aria-label="Output tokens per model call" data-test="max-tokens" type="text" inputmode="numeric" autocomplete="off" placeholder="Gateway limit" />
        </SettingRow>
        <SettingRow setting-id="max-tool-rounds" label="Model/tool rounds"
          description="Maximum model calls in the tool loop. A round can request several tools; allow another round for the final answer. Blank uses the gateway's configured default."
          :modified="!!maxToolRounds.trim()" @reset="maxToolRounds = ''">
          <input v-model="maxToolRounds" class="limit-input" aria-label="Model/tool rounds" data-test="max-tool-rounds" type="text" inputmode="numeric" autocomplete="off" placeholder="Gateway default" />
        </SettingRow>
      </fieldset>

      <RouterPolicyForm v-if="isRouter" v-model="decision" :busy="busy" />
      <fieldset v-else>
        <legend>Behaviour</legend>
        <label class="field"><span>Identity (replaces the shared identity line)</span><textarea v-model="identity" data-test="identity" rows="2" placeholder="Empty = the shared identity from Shared prompts" /></label>
        <label class="field"><span>Persona</span><textarea v-model="persona" data-test="persona" rows="3" /></label>
        <label class="field"><span>Instructions</span><textarea v-model="instructions" data-test="instructions" rows="8" placeholder="Empty = the shared default instructions" /></label>
        <label class="field"><span>Focus</span><input v-model="focus" data-test="focus" type="text" autocomplete="off" placeholder="One line the entry agent uses to pick this specialist" /></label>
        <ToolScopePicker v-model="allow" :capabilities="capabilities" />
        <div class="row">
          <label class="field grow"><span>Allowed tools</span><input v-model="allow" data-test="allow" type="text" autocomplete="off" placeholder="All tools, or e.g. calc_*, convert_*" /></label>
          <label class="field grow"><span>Denied tools</span><input v-model="deny" data-test="deny" type="text" autocomplete="off" placeholder="None" /></label>
        </div>
      </fieldset>

      <div class="switches">
        <ToggleSwitch :checked="enabled" data-test="enabled" @change="enabled = ($event.target as HTMLInputElement).checked">Enabled</ToggleSwitch>
        <ToggleSwitch v-if="!isRouter" :checked="orchestrator" :disabled="isLaya" data-test="orchestrator" @change="orchestrator = ($event.target as HTMLInputElement).checked">Orchestrator (can hand work to other agents)</ToggleSwitch>
        <ToggleSwitch v-if="!isRouter" :checked="planTool" :disabled="isLaya" data-test="plan-tool" @change="planTool = ($event.target as HTMLInputElement).checked">Task checklist (can show a step-by-step plan; chats can also turn it off)</ToggleSwitch>
        <ToggleSwitch v-if="!isRouter" :checked="entry" :disabled="isLaya" data-test="entry" @change="entry = ($event.target as HTMLInputElement).checked">Entry agent (receives every new question)</ToggleSwitch>
      </div>
      <p v-if="planTool && !isLaya" class="hint" data-test="plan-tool-cost">Task checklist costs about 200 input tokens on every model call of this agent, plus about 15-25 output tokens per item each time it updates the list. Turn it off for agents that only do short tasks.</p>
      <p v-if="entry" class="hint">Only one enabled agent can be the entry agent. To move it, unset it on the current one first.</p>

      <fieldset v-if="!isRouter" class="preview">
        <legend>Prompt preview</legend>
        <p class="hint">The system prompt the model receives, built from this form and the shared prompts.</p>
        <div class="row preview-bar">
          <ToggleSwitch :checked="previewCaveman" data-test="preview-caveman" @change="previewCaveman = ($event.target as HTMLInputElement).checked">Preview with the chat's caveman toggle on</ToggleSwitch>
          <button type="button" class="cancel" data-test="preview" :disabled="previewing" @click="previewPrompt">{{ previewing ? "Building…" : "Show prompt" }}</button>
        </div>
        <p v-if="previewError" class="error" role="alert" data-test="preview-error">{{ previewError }}</p>
        <pre v-if="previewText" class="prompt-text" data-test="preview-text">{{ previewText }}</pre>
      </fieldset>

      <p v-if="localError || error" class="error" role="alert" data-test="form-error">{{ localError || error }}</p>
      <div class="actions">
        <span v-if="modified" class="unsaved" role="status" data-test="unsaved">● Unsaved changes</span>
        <button type="button" class="cancel" :disabled="busy" @click="emit('close')">Cancel</button>
        <button type="submit" class="primary" :disabled="busy" data-test="save">{{ busy ? "Saving…" : editing ? "Save" : "Create" }}</button>
      </div>
    </form>
  </BaseModal>
</template>

<style scoped>
.agent-form { display: grid; gap: 12px; }
.row { display: flex; flex-wrap: wrap; gap: 10px; }
.grow { flex: 1 1 160px; }
.port { flex: 0 0 110px; }
.field { display: grid; gap: 4px; min-width: 0; font-size: 0.9em; }
.field > span { color: var(--muted); }
.field small, .hint { color: var(--muted); font-size: 0.8em; }
.hint { margin: 0; }
input:not([type="checkbox"]), select, textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  background: var(--bg);
  font: inherit;
}
textarea { resize: vertical; }
input.limit-input { width: 160px; max-width: 100%; }
input:disabled, select:disabled { opacity: 0.6; }
fieldset { display: grid; gap: 10px; margin: 0; padding: 10px 12px 12px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
legend { padding: 0 6px; color: var(--muted); font-size: 0.85em; }
.tier-preview { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; font-size: 0.85em; }
.tier-preview li { display: grid; grid-template-columns: 70px minmax(0, 1fr) auto; gap: 10px; }
.tier-preview li.off { color: var(--muted); text-decoration: line-through; }
.tier-preview code { font-family: var(--mono); overflow-wrap: anywhere; }
.tier-preview .where { color: var(--muted); text-decoration: none; }
.switches { display: grid; gap: 8px; }
.preview-bar { align-items: center; justify-content: space-between; }
.prompt-text { max-height: 280px; margin: 0; padding: 10px 12px; overflow: auto; border-radius: var(--radius-md); background: var(--code-bg); color: var(--text); font-family: var(--mono); font-size: 0.8em; white-space: pre-wrap; overflow-wrap: anywhere; }
.actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
.unsaved { margin-right: auto; color: var(--muted); font-size: 0.8em; }
.unsaved::first-letter { color: var(--accent); }
.cancel { padding: 6px 16px; border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text); font: inherit; cursor: pointer; }
.primary { padding: 6px 16px; border: none; border-radius: var(--radius-full); cursor: pointer; font: inherit; font-weight: 600; color: var(--accent-contrast); background: var(--accent); }
.primary:disabled, .cancel:disabled { opacity: 0.6; cursor: default; }
.error { margin: 0; color: var(--danger); }
:is(button, input, select, textarea):focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
