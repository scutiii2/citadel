<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type OutsideGroup, type OutsideOrigin, type OutsideView } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

type Target = { group: OutsideGroup; origin?: OutsideOrigin };
type ViewError = { message: string; serviceId?: string; deleteId?: string };

const groups = ref<OutsideGroup[]>([]);
const drafts = ref<Record<string, string>>({});
const loading = ref(true);
const renaming = ref<string | null>(null);
const removing = ref(false);
const busy = computed(() => renaming.value !== null || removing.value);
const error = ref<ViewError | null>(null);
const target = ref<Target | null>(null);

function applyView(next: OutsideView, renamedId?: string) {
  const previousNames = new Map(groups.value.map((group) => [group.service_id, group.name]));
  drafts.value = Object.fromEntries(next.groups.map(({ service_id: id, name }) => {
    const draft = drafts.value[id];
    const keepDraft = id !== renamedId && draft !== undefined && draft !== previousNames.get(id);
    return [id, keepDraft ? draft : name];
  }));
  groups.value = next.groups;
}

onMounted(async () => {
  try {
    applyView(await treasuryAdminClient.getOutside());
  } catch (err) {
    error.value = { message: errorMessage(err) };
  } finally {
    loading.value = false;
  }
});

async function rename(group: OutsideGroup) {
  const id = group.service_id;
  const name = drafts.value[id]?.trim();
  if (busy.value || !name || name === group.name) return;
  renaming.value = id;
  error.value = null;
  try {
    const renamed = await treasuryAdminClient.renameOutside(id, name);
    applyView({ groups: groups.value.map((row) => row.service_id === id ? renamed : row) }, id);
    try {
      applyView(await treasuryAdminClient.getOutside());
    } catch (err) {
      error.value = { message: `Name saved. Could not refresh outside services. ${errorMessage(err)}` };
    }
  } catch (err) {
    error.value = { serviceId: id, message: errorMessage(err) };
  } finally {
    renaming.value = null;
  }
}

const message = computed(() => {
  const current = target.value;
  if (!current) return "";
  const question = current.origin
    ? `Remove ${current.origin.origin} from ${current.group.name}?`
    : `Remove ${current.group.name} and all its origins?`;
  return current.group.used_by.length
    ? `${question} In use by ${current.group.used_by.join(", ")}. Removing this entry can disrupt their connections.`
    : question;
});

function closeConfirmation() {
  if (!removing.value) target.value = null;
}

async function remove() {
  const current = target.value;
  if (!current || busy.value) return;
  removing.value = true;
  error.value = null;
  try {
    const next = current.origin
      ? await treasuryAdminClient.deleteOutsideOrigin(current.origin.origin_id)
      : await treasuryAdminClient.deleteOutsideGroup(current.group.service_id);
    applyView(next);
  } catch (err) {
    error.value = { message: errorMessage(err), deleteId: current.origin?.origin_id ?? current.group.service_id };
  } finally {
    removing.value = false;
    closeConfirmation();
  }
}
</script>

<template>
  <PageLayout class="info-content" title="Outside services">
    <p v-if="error && !error.serviceId && !error.deleteId" class="error" role="alert">{{ error.message }}</p>
    <p v-if="loading" class="muted" role="status">Loading…</p>
    <p v-else-if="!error && !groups.length" class="muted">No outside services yet.</p>
    <div v-else-if="groups.length" class="table-wrap" role="region" aria-label="Outside services" tabindex="0">
      <table>
        <thead>
          <tr><th scope="col">Name</th><th scope="col">Origins</th><th scope="col">Used by</th><th scope="col">Remove</th></tr>
        </thead>
        <tbody>
          <tr v-for="group in groups" :key="group.service_id" :data-test="'group-' + group.name">
            <td>
              <form class="rename-form" @submit.prevent="rename(group)">
                <label :for="'name-' + group.service_id">Name of {{ group.name }}</label>
                <input
                  :id="'name-' + group.service_id"
                  v-model="drafts[group.service_id]"
                  :disabled="busy"
                  :aria-invalid="error?.serviceId === group.service_id || undefined"
                  :aria-describedby="error?.serviceId === group.service_id ? 'error-' + group.service_id : undefined"
                  autocomplete="off"
                  spellcheck="false"
                />
                <p v-if="error?.serviceId === group.service_id" :id="'error-' + group.service_id" class="error" role="alert">
                  {{ error.message }}
                </p>
                <button
                  type="submit"
                  class="primary"
                  :disabled="busy || !drafts[group.service_id]?.trim() || drafts[group.service_id]?.trim() === group.name"
                  :aria-busy="renaming === group.service_id"
                >Rename</button>
              </form>
            </td>
            <td>
              <ul v-if="group.origins.length" class="origins">
                <li v-for="origin in group.origins" :key="origin.origin_id">
                  <code>{{ origin.origin }}</code>
                  <button
                    type="button"
                    class="danger"
                    :data-test="'delete-origin-' + origin.origin_id"
                    :aria-label="'Remove origin ' + origin.origin"
                    :aria-describedby="error?.deleteId === origin.origin_id ? 'delete-origin-error-' + origin.origin_id : undefined"
                    :disabled="busy"
                    @click="target = { group, origin }"
                  >Remove origin</button>
                  <p v-if="error?.deleteId === origin.origin_id" :id="'delete-origin-error-' + origin.origin_id" class="error delete-error" role="alert">
                    {{ error.message }}
                  </p>
                </li>
              </ul>
              <span v-else class="muted">No origins</span>
            </td>
            <td>{{ group.used_by.length ? group.used_by.join(", ") : "Not used" }}</td>
            <td>
              <button
                type="button"
                class="danger"
                data-test="delete-group"
                :aria-label="'Remove service ' + group.name"
                :aria-describedby="error?.deleteId === group.service_id ? 'delete-service-error-' + group.service_id : undefined"
                :disabled="busy"
                @click="target = { group }"
              >Remove service</button>
              <p v-if="error?.deleteId === group.service_id" :id="'delete-service-error-' + group.service_id" class="error delete-error" role="alert">
                {{ error.message }}
              </p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ConfirmModal
      :open="target !== null"
      :title="target?.origin ? 'Remove origin' : 'Remove outside service'"
      :message="message"
      confirm-label="Remove"
      danger
      :busy="removing"
      @confirm="remove"
      @close="closeConfirmation"
    />
  </PageLayout>
</template>

<style scoped>
.rename-form { display: grid; gap: 8px; min-width: 190px; }
.rename-form label { font-size: 0.85em; color: var(--muted); overflow-wrap: anywhere; }
.rename-form input { min-height: 44px; width: 100%; }
.rename-form .error { margin: 0; overflow-wrap: anywhere; }
.origins { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.origins li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.origins code { min-width: 0; overflow-wrap: anywhere; }
.delete-error { flex-basis: 100%; margin: 4px 0 0; overflow-wrap: anywhere; }
@media (pointer: coarse), (max-width: 767px) {
  button { min-width: 44px; min-height: 44px; }
}
</style>
