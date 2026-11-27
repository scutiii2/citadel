<script setup lang="ts">
import { AdminSearch, ToggleSwitch } from "@citadel/ui";
import { computed, ref } from "vue";
import type { AccountUsage } from "../../api/UsageClient";
import SegmentedControl from "../SegmentedControl.vue";

/** Who an action is for: every enabled account, or the ones switched on in the list. */
const props = defineProps<{ accounts: AccountUsage[]; disabled?: boolean }>();
const all = defineModel<boolean>("all", { required: true });
const ids = defineModel<number[]>("ids", { required: true });

const WHO: { value: "selected" | "all"; label: string }[] = [
  { value: "selected", label: "Selected" }, { value: "all", label: "All users" },
];
const who = computed<"selected" | "all">({
  get: () => (all.value ? "all" : "selected"),
  set: (value) => { all.value = value === "all"; },
});
const search = ref("");
const enabled = computed(() => props.accounts.filter((account) => account.is_active).length);
const shown = computed(() => {
  const query = search.value.trim().toLowerCase();
  return props.accounts
    .filter((account) => account.username.toLowerCase().includes(query))
    .sort((a, b) => a.username.localeCompare(b.username));
});

function choose(id: number, event: Event): void {
  const on = (event.target as HTMLInputElement).checked;
  ids.value = on ? [...ids.value, id] : ids.value.filter((other) => other !== id);
}
</script>

<template>
  <fieldset class="recipients" :disabled="disabled">
    <legend>Recipients</legend>
    <SegmentedControl v-model="who" :options="WHO" aria-label="Recipients" />
    <p v-if="all" class="muted">Every enabled account: {{ enabled }}. Accounts created later get nothing.</p>
    <template v-else>
      <AdminSearch v-model="search" label="Search recipients" />
      <p v-if="!shown.length" class="muted">No users match.</p>
      <ul v-else class="list">
        <li v-for="account in shown" :key="account.account_id">
          <ToggleSwitch small :checked="ids.includes(account.account_id)" :data-test="`recipient-${account.account_id}`" @change="choose(account.account_id, $event)">
            {{ account.username }}<span v-if="!account.is_active" class="muted"> (disabled)</span>
          </ToggleSwitch>
        </li>
      </ul>
      <p class="muted" role="status">{{ ids.length }} selected</p>
    </template>
  </fieldset>
</template>

<style scoped>
.recipients { display: grid; gap: 8px; min-width: 0; margin: 0; padding: 0; border: 0; }
legend { margin-bottom: 8px; padding: 0; font-size: 0.9em; font-weight: 600; }
.list { display: grid; max-height: 260px; margin: 0; padding: 4px 10px; overflow: auto; scrollbar-gutter: stable; list-style: none; border: 1px solid var(--border); border-radius: var(--radius-md); }
.list li { display: flex; align-items: center; min-width: 0; min-height: 36px; overflow-wrap: anywhere; }
.muted { margin: 0; color: var(--muted); font-size: 0.85em; }
@media (max-width: 767px) { .list li { min-height: 44px; } }
</style>
