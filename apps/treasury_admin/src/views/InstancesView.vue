<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type TreasuryInstance, type TreasuryView } from "../api/TreasuryAdminClient";
import { AdminSearch } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { RecordDrawer } from "@citadel/ui";
import { PageLayout } from "@citadel/ui";
import { useNoticesStore } from "../stores/notices";
import { errorMessage } from "../utils/errors";
import "@citadel/ui/admin.css";

/** The databases Treasury serves: a read-only roster. Each service registers its own instance, so this page only
 * shows them; the connections they use are on the Connections page. */
const notices = useNoticesStore();
const view = ref<TreasuryView | null>(null);
const error = ref("");
const loading = ref(true);
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const selectedName = ref<string | null>(null);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    view.value = await treasuryAdminClient.get();
    notices.report(view.value.reachable);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const visible = computed<TreasuryInstance[]>(() => {
  const query = search.value.trim().toLowerCase();
  return (view.value?.instances ?? []).filter((i) => [i.name, ...i.connections].some((text) => text.toLowerCase().includes(query)));
});
const selected = computed(() => view.value?.instances.find((i) => i.name === selectedName.value) ?? null);
const usedByPortcullis = (name: string) => view.value?.portcullis.instance === name;
</script>

<template>
  <PageLayout class="admin-panel" title="Instances" wide>
    <section class="admin-panel-card" aria-labelledby="instance-roster">
      <header class="admin-panel-head">
        <h2 id="instance-roster">Instance roster</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Instance roster"><p>The databases Treasury serves. Each instance lists the connections it may use. Each service registers its own, so this page only shows them.</p><p>The connections they use are on the Connections page.</p></PanelHelp>
          <button type="button" class="admin-icon" data-test="refresh" aria-label="Refresh instances" title="Refresh instances" :disabled="loading" @click="load"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" /></svg></button>
          <AdminSearch ref="searchField" v-model="search" label="Search instances" />
        </div>
      </header>
      <p v-if="loading && !view" class="admin-panel-text muted" role="status">Loading…</p>
      <ActionMessage v-else-if="error" kind="error" :text="error" class="admin-panel-text" />
      <ActionMessage v-else-if="view && !view.reachable" kind="error" :text="`Treasury does not answer. Check that it is running.`" class="admin-panel-text" />
      <p v-else-if="!view?.instances.length" class="admin-panel-text muted">No instances yet.</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No instances match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="instance-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Instance</th><th scope="col">Connections</th></tr></thead>
          <tbody>
            <tr v-for="i in visible" :key="i.name" data-test="instance">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="selectedName = i.name">{{ i.name }}</button><span v-if="usedByPortcullis(i.name)" class="badge">Portcullis</span></th>
              <td class="muted">{{ i.connections.length ? i.connections.join(", ") : "No connections" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="view?.reachable && view.instances.length" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ view.instances.length }} instances</p>
    </section>

    <RecordDrawer :open="selected !== null" :title="selected ? `Instance ${selected.name}` : 'Instance details'" :fallback-focus="() => searchField?.focus()" @close="selectedName = null">
      <div v-if="selected" class="admin-details">
        <dl>
          <dt>Name</dt><dd>{{ selected.name }}</dd>
          <dt>Connections</dt><dd>{{ selected.connections.length ? selected.connections.join(", ") : "No connections" }}</dd>
        </dl>
        <p v-if="usedByPortcullis(selected.name)" class="muted" data-test="portcullis">
          Portcullis stores its data here, in connection "{{ view?.portcullis.connection }}".
        </p>
      </div>
    </RecordDrawer>
  </PageLayout>
</template>

<style scoped>
.badge { margin-inline-start: 8px; padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--muted); font-size: 0.75em; }
.count { border-top: 1px solid var(--border); font-size: 0.85em; }
</style>
