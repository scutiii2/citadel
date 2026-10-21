<script setup lang="ts">
import type { RouterPolicy } from "../../api/AgentsAdminClient";
import ToggleSwitch from "../ToggleSwitch.vue";

const props = defineProps<{ modelValue: RouterPolicy; busy: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: RouterPolicy] }>();
type SwitchKey = "choose_agent" | "choose_tier" | "english" | "typed" | "fallback" | "trace";
const switches: { key: SwitchKey; label: string }[] = [
  { key: "choose_agent", label: "Choose a specialist" }, { key: "choose_tier", label: "Choose a model tier" },
  { key: "english", label: "Laya English (local, first voter)" },
  { key: "typed", label: "Laya typed-decisions (local, second voter)" },
  { key: "fallback", label: "Jev fallback when local models cannot settle" },
  { key: "trace", label: "Record decision trace metadata" },
];
const counts = ["2", "3+"] as const;
const voters = ["laya-english", "laya-typed", "jev"] as const;
const sizes = ["tiny", "everyday", "large", "hardest"] as const;
const tiers = ["light", "standard", "heavy", "extreme"];
function update(key: keyof RouterPolicy, value: unknown) {
  emit("update:modelValue", { ...props.modelValue, [key]: value });
}
function threshold(count: typeof counts[number], voter: typeof voters[number], event: Event) {
  update("thresholds", { ...props.modelValue.thresholds,
    [count]: { ...props.modelValue.thresholds[count], [voter]: Number((event.target as HTMLInputElement).value) } });
}
</script>

<template>
  <fieldset class="router-policy" :aria-busy="busy">
    <legend>Routing decisions</legend>
    <p class="hint">Chooses an agent and model tier. It has no tools, chat role or memory access.</p>
    <ToggleSwitch v-for="item in switches" :key="item.key" :checked="modelValue[item.key]" :disabled="busy"
      :data-test="`router-${item.key}`" @change="update(item.key, ($event.target as HTMLInputElement).checked)">{{ item.label }}</ToggleSwitch>
    <p class="hint">Local models: convaiinnovations/laya and typed-decisions. Jev uses the deployment's configured fallback. Confidence thresholds are decision scores, not measured accuracy.</p>
    <div class="fields">
      <label>Routing deadline (seconds)<input :value="modelValue.deadline_seconds" type="number" min="1" max="30" step="any" required :disabled="busy" data-test="routing-deadline" @input="update('deadline_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>Remote timeout (seconds)<input :value="modelValue.remote_timeout_seconds" type="number" min="0.01" max="30" step="any" required :disabled="busy" @input="update('remote_timeout_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>Prune ratio [0, 1)<input :value="modelValue.prune_ratio" type="number" min="0" max="0.9999" step="any" required :disabled="busy" @input="update('prune_ratio', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>Pair ratio (0, 1]<input :value="modelValue.pair_ratio" type="number" min="0.0001" max="1" step="any" required :disabled="busy" @input="update('pair_ratio', Number(($event.target as HTMLInputElement).value))" /></label>
    </div>
    <fieldset v-for="count in counts" :key="count">
      <legend>{{ count }} options: confidence thresholds</legend>
      <div class="fields"><label v-for="voter in voters" :key="voter">{{ voter }}<input :value="modelValue.thresholds[count][voter]" type="number" min="0" max="1" step="0.01" required :disabled="busy" @input="threshold(count, voter, $event)" /></label></div>
    </fieldset>
    <fieldset><legend>Request size to model tier</legend>
      <div class="fields"><label v-for="size in sizes" :key="size">{{ size }}<select :value="modelValue.size_tiers[size]" :disabled="busy"
        @change="update('size_tiers', { ...modelValue.size_tiers, [size]: ($event.target as HTMLSelectElement).value })"><option v-for="tier in tiers" :key="tier">{{ tier }}</option></select></label></div>
      <p class="hint">The selected agent's model limits still apply. Uncertain decisions use ordinary chat defaults.</p>
    </fieldset>
  </fieldset>
</template>

<style scoped>
.router-policy { display: grid; gap: 12px; min-width: 0; border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px; }
fieldset { min-width: 0; border: 1px solid var(--border); border-radius: var(--radius-md); }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
label { display: grid; gap: 4px; font-size: .85em; color: var(--muted); }
input, select { min-width: 0; width: 100%; box-sizing: border-box; padding: 7px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--text); font: inherit; }
.hint { margin: 0; color: var(--muted); font-size: .85em; }
</style>
