<script setup lang="ts">
import type { ForgeGroup, ForgeMode } from "../api/ForgeClient";
import { MODE_HELP, MODE_OPTIONS } from "../utils/forgeModes";
import SegmentedControl from "./SegmentedControl.vue";
import ToggleSwitch from "./ToggleSwitch.vue";

defineProps<{ group: ForgeGroup; busy: boolean }>();
const emit = defineEmits<{
  mode: [mode: ForgeMode];
  "full-auto": [];
  relay: [on: boolean];
  invite: [];
  remove: [workerId: number];
  delete: [];
}>();

function chooseMode(next: ForgeMode, current: ForgeMode): void {
  if (next === current) return;
  if (next === "full_auto") emit("full-auto");
  else emit("mode", next);
}
</script>

<template>
  <aside class="panel" :aria-busy="busy">
    <section>
      <h3>Workers</h3>
      <ul v-if="group.members.length" class="members">
        <li v-for="m in group.members" :key="m.worker_id">
          <div class="line">
            <strong class="who">@{{ m.label }}</strong>
            <span class="provider">{{ m.provider }}</span>
            <button type="button" class="remove" :aria-label="`Remove @${m.label} from this group`" :disabled="busy" @click="emit('remove', m.worker_id)">Remove</button>
          </div>
          <code class="folder">{{ m.folder }}</code>
          <span class="status" :class="{ online: m.online }">
            <svg v-if="m.online" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5" /></svg>
            <svg v-else viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><circle cx="12" cy="12" r="8" /></svg>
            {{ m.online ? "Online" : "Offline" }}
          </span>
        </li>
      </ul>
      <p v-else class="muted">No workers yet.</p>
      <button type="button" class="invite" :disabled="busy" @click="emit('invite')">Invite a worker</button>
    </section>

    <section>
      <h3>Mode</h3>
      <SegmentedControl
        :model-value="group.mode"
        :options="MODE_OPTIONS"
        aria-label="Group mode"
        @update:model-value="(next: ForgeMode) => chooseMode(next, group.mode)"
      />
      <p class="muted help">{{ MODE_HELP[group.mode] }}</p>
    </section>

    <section>
      <h3>Hand-over</h3>
      <ToggleSwitch :checked="group.relay" :disabled="busy" @change="emit('relay', ($event.target as HTMLInputElement).checked)">
        Let workers hand over to each other
      </ToggleSwitch>
      <p class="muted help">A reply that ends with a line starting @name passes the turn on, up to three times in a row.</p>
    </section>

    <section class="danger-zone">
      <h3>Danger zone</h3>
      <button type="button" class="delete" :disabled="busy" @click="emit('delete')">Delete group</button>
    </section>
  </aside>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow-y: auto;
}
h3 {
  margin: 0 0 6px;
  font-size: 1em;
  font-weight: 600;
}
.members {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.members li {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.who {
  color: var(--accent);
}
.provider,
.muted,
.status {
  color: var(--muted);
  font-size: 0.85em;
}
.folder {
  font-family: var(--mono);
  font-size: 0.85em;
  overflow-wrap: anywhere;
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.status.online {
  color: var(--success);
}
.status svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.help {
  margin: 6px 0 0;
}
button.remove {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.85em;
  text-decoration: underline;
  cursor: pointer;
}
button.invite {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  border-radius: var(--radius-full);
  padding: 6px 14px;
  font: inherit;
  cursor: pointer;
}
button.invite:hover {
  border-color: var(--accent);
}
.danger-zone {
  border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--border));
  background: color-mix(in srgb, var(--danger) 6%, var(--bg));
  border-radius: var(--radius-lg);
  padding: 10px 12px;
}
button.delete {
  border: 1px solid var(--danger);
  background: transparent;
  color: var(--danger);
  border-radius: var(--radius-full);
  padding: 6px 14px;
  font: inherit;
  cursor: pointer;
}
</style>
