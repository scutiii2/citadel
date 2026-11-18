<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { toolTokensClient, type ToolService, type ToolTokensKind } from "../api/ToolTokensClient";
import PasswordInput from "./PasswordInput.vue";
import { errorMessage } from "../utils/errors";

/** The tokens this service presents to the tool services (Bard, Scribe, Reader). Each tool service makes one per caller
 * on its own admin page (Tokens card). Saved in this service's database and used by the next request. A token is
 * write-only: the card only says whether one is in use. */
const props = defineProps<{ kind: ToolTokensKind; title: string }>();

const services = ref<ToolService[]>([]);
const typed = ref<Record<string, string>>({});
const removing = ref<Set<string>>(new Set());
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const changes = computed(() => {
  const out: Record<string, string | null> = {};
  for (const service of services.value) {
    if (removing.value.has(service.name)) out[service.name] = null;
    else if (typed.value[service.name]) out[service.name] = typed.value[service.name];
  }
  return out;
});
const changed = computed(() => Object.keys(changes.value).length > 0);

function apply(list: ToolService[]) {
  services.value = list;
  typed.value = {};
  removing.value = new Set();
}

function toggleRemove(name: string) {
  const next = new Set(removing.value);
  if (next.has(name)) next.delete(name);
  else {
    next.add(name);
    delete typed.value[name];
  }
  removing.value = next;
}

onMounted(async () => {
  try {
    apply(await toolTokensClient.list(props.kind));
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await toolTokensClient.save(props.kind, changes.value));
    notice.value = "Saved. The next request uses it.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="card" :aria-labelledby="`${kind}-tokens-title`">
    <h2 :id="`${kind}-tokens-title`" class="title">{{ title }}</h2>
    <p class="help">Make a token on each tool service's admin page (Tokens card) and paste it here. It is never shown again.</p>
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else class="fields" data-test="form" @submit.prevent="save">
      <div v-for="service in services" :key="service.name" class="field" :data-test="`row-${service.name}`">
        <PasswordInput
          :model-value="typed[service.name] ?? ''"
          :label="service.label"
          autocomplete="off"
          data-test="token"
          :disabled="saving || removing.has(service.name)"
          :placeholder="service.has_token ? 'A token is in use. Type to replace it.' : 'No token yet'"
          @update:model-value="typed[service.name] = $event"
        />
        <button v-if="service.stored" type="button" class="chip" data-test="remove" :disabled="saving" @click="toggleRemove(service.name)">
          {{ removing.has(service.name) ? "Keep it" : "Remove the saved token" }}
        </button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.card { display: grid; gap: 12px; max-width: 560px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.fields { display: grid; gap: 16px; }
.field { display: grid; gap: 6px; min-width: 0; justify-items: start; }
.field :deep(input) { min-height: 44px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
.muted { margin: 0; color: var(--muted); }
.actions { display: flex; justify-content: flex-end; }
</style>
