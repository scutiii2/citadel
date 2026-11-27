<script setup lang="ts">
// The account's free resets, the automatic-use switch and active boosts, in the usage ring's panel and on the Usage
// page. Nothing shows with a server that has no resets.
import { computed, ref, watch } from "vue";
import { ConfirmModal, ToggleSwitch } from "@citadel/ui";
import { useUsageLimitsStore } from "../stores/usageLimits";
import { boostLines, cachedText, confirmText, resetGroups, type ResetGroup } from "../utils/resets";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";

/** `changed`: a reset was used, so numbers shown elsewhere are out of date. */
const emit = defineEmits<{ changed: [] }>();

const store = useUsageLimitsStore();
const overview = computed(() => (store.usage?.resets ? store.usage : null));
const groups = computed(() => (overview.value ? resetGroups(overview.value.resets ?? [], overview.value) : []));
const boosts = computed(() => (overview.value ? boostLines(overview.value) : []));
const cached = computed(() => cachedText(overview.value?.cached_token_weight));

const asking = ref<ResetGroup | null>(null);
const spending = ref(false);
const switching = ref(false);
const error = ref("");

async function spend(): Promise<void> {
  const chosen = asking.value;
  if (!chosen || spending.value) return;
  spending.value = true;
  error.value = "";
  try {
    await store.spend(chosen.next.id);
    emit("changed");
  } catch (err) {
    error.value = errorMessage(err);
    void store.load(); // it may be used or expired already
  }
  spending.value = false;
  asking.value = null;
}

function dismiss(): void {
  if (!spending.value) asking.value = null;
}

async function toggleAuto(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const wanted = input.checked;
  input.checked = !wanted; // the saved value stays until the server answers
  if (switching.value) return;
  switching.value = true;
  error.value = "";
  try {
    await store.setAutoUse(wanted);
  } catch (err) {
    error.value = errorMessage(err);
  }
  switching.value = false;
}

watch(() => overview.value === null, (gone) => {
  if (!gone) return;
  asking.value = null;
  error.value = "";
});
</script>

<template>
  <section v-if="overview" class="resets" aria-label="Free resets">
    <h3>Free resets</h3>
    <p v-if="!groups.length" class="note">You have no free resets.</p>
    <ul v-else>
      <li v-for="group in groups" :key="group.kind">
        <span class="what">
          <strong>{{ group.title }}<template v-if="group.count > 1"> ×{{ group.count }}</template></strong>
          <span class="note">{{ group.next.expires_at ? `${group.count > 1 ? "Next expires" : "Expires"} ${formatUtc(group.next.expires_at)}` : "No expiry" }}</span>
          <span v-if="!group.clears" class="note">Nothing to clear yet.</span>
        </span>
        <button type="button" class="pill-btn" :data-test="`use-${group.kind}`" :aria-label="`Use ${group.title.toLowerCase()}`" :disabled="!group.clears || spending" @click="asking = group">Use</button>
      </li>
    </ul>
    <div class="auto">
      <ToggleSwitch small data-test="auto-reset" :checked="overview.auto_use === true" :disabled="switching" :aria-busy="switching" @change="toggleAuto">Use automatically</ToggleSwitch>
      <p class="note" role="status">{{ switching ? "Saving…" : "Spends a free reset when a question would be blocked." }}</p>
    </div>
    <p v-for="line in boosts" :key="line" class="boost">{{ line }}</p>
    <p v-if="cached" class="note">{{ cached }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <ConfirmModal
      :open="asking !== null"
      :title="asking ? `Use ${asking.title.toLowerCase()}?` : ''"
      :message="asking ? confirmText(asking.kind) : ''"
      confirm-label="Use reset"
      :busy="spending"
      @confirm="spend"
      @close="dismiss"
    />
  </section>
</template>

<style scoped>
.resets {
  display: grid;
  gap: 8px;
  min-width: 0;
}
h3 {
  margin: 0;
  font-size: 1em;
}
ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.what {
  display: grid;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 0.85rem;
}
/* Not the quiet `ghost` pill: its muted text reads as switched off beside a disabled one. */
li > button {
  flex: none;
  color: var(--text);
  background: transparent;
}
.auto {
  display: grid;
  justify-items: start;
  gap: 2px;
}
.note,
.boost,
.error {
  margin: 0;
  font-size: 0.75rem;
}
.note {
  color: var(--muted);
}
.error {
  color: var(--danger);
}
@media (max-width: 767px) {
  li > button {
    min-height: 44px;
    min-width: 64px;
  }
}
</style>
