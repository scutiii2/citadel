<script setup lang="ts">
import { onMounted, ref } from "vue";
import { treasuryAdminClient, type ServicesView } from "../api/TreasuryAdminClient";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

const { getServices, putService, deleteService } = treasuryAdminClient;
const view = ref<ServicesView | null>(null);
const drafts = ref<Record<string, string>>({});
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const labels = { pinned: "Pinned", registered: "Registered", default: "Default" };

function applyView(next: ServicesView) {
  view.value = next;
  for (const row of next.services) drafts.value[row.name] ??= row.pinned ?? row.url;
}

onMounted(async () => {
  try { applyView(await getServices()); }
  catch (err) { error.value = errorMessage(err); }
  finally { loading.value = false; }
});

/** Wait for Treasury confirmation before changing the displayed address. */
async function save(name: string, unpin = false) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const next = unpin ? await deleteService(name) : await putService(name, String(drafts.value[name]).trim());
    applyView(next);
    const row = next.services.find((service) => service.name === name);
    if (row) drafts.value[name] = row.pinned ?? row.url;
  } catch (err) { error.value = errorMessage(err); }
  finally { busy.value = false; }
}
</script>

<template>
  <PageLayout class="info-content services" title="Services" description="Where Citadel services can reach each other. A pinned address takes precedence over registration.">
    <p v-if="error" class="error" role="alert" id="service-error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading…</p>
    <div v-else-if="view" class="table-scroll" role="region" aria-label="Service addresses" tabindex="0">
      <table>
        <thead><tr><th>Name</th><th>Address in use</th><th>Source</th><th>Pin an address</th></tr></thead>
        <tbody>
          <tr v-for="row in view.services" :key="row.name" :data-test="'row-' + row.name">
            <td><code>{{ row.name }}</code></td>
            <td>{{ row.url }}</td>
            <td>{{ labels[row.source] }}</td>
            <td>
              <form class="pin-form" @submit.prevent="save(row.name)">
                <label :for="'pin-' + row.name">Address for {{ row.name }}</label>
                <input :id="'pin-' + row.name" v-model="drafts[row.name]" :disabled="busy" :aria-describedby="error ? 'service-error' : undefined" autocomplete="off" spellcheck="false" />
                <div class="actions">
                  <button type="submit" class="primary" :disabled="busy || !String(drafts[row.name] ?? '').trim()" :aria-busy="busy">Pin</button>
                  <button v-if="row.pinned" type="button" class="chip" data-test="unpin" :disabled="busy" :aria-busy="busy" @click="save(row.name, true)">Use the registered address</button>
                </div>
              </form>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </PageLayout>
</template>

<style scoped>
.table-scroll { overflow-x: auto; }
.pin-form { display: grid; gap: 8px; min-width: 220px; }
.pin-form label { font-size: 0.85em; color: var(--muted); }
.pin-form input { min-height: 44px; width: 100%; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
