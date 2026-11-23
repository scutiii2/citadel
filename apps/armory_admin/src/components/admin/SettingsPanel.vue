<script setup lang="ts">
import { ref, toRef, useId } from "vue";
import { useDraftPanel } from "../../composables/useDraftPanel";
import PageLayout from "../PageLayout.vue";
import AdminSearch from "./AdminSearch.vue";
import ConfirmModal from "./ConfirmModal.vue";
import DraftActions from "./DraftActions.vue";
import PanelHelp from "./PanelHelp.vue";
import "./admin.css";

/** A settings page as one admin panel: the header holds the help popover, the Cancel and Save icons (only while
 * the draft differs from what is saved) and a search. The body is the page's sections; a section hides itself
 * with `v-show` on the search text, so a hidden field keeps its draft. Copy kept in every admin app. */
const props = defineProps<{ title: string; heading: string; label: string; dirty: boolean; saving: boolean }>();
const emit = defineEmits<{ discard: []; save: [] }>();
const search = defineModel<string>("search", { default: "" });
const field = ref<InstanceType<typeof AdminSearch>>();
const titleId = useId();
const { discardOpen, keepFocus, answerDiscard } = useDraftPanel(toRef(props, "dirty"), field);

/** Whether a section or field with these texts is shown for the current search. */
function matches(...texts: (string | undefined)[]): boolean {
  const query = search.value.trim().toLowerCase();
  return !query || texts.some((text) => text?.toLowerCase().includes(query));
}

defineExpose({ keepFocus, focusSearch: () => field.value?.focus(), matches });
</script>

<template>
  <PageLayout class="admin-panel" :title="title" wide>
    <section class="admin-panel-card" :aria-labelledby="titleId">
      <header class="admin-panel-head">
        <h2 :id="titleId">{{ heading }}</h2>
        <div class="admin-panel-tools settings-tools">
          <PanelHelp :title="heading"><slot name="help" /></PanelHelp>
          <slot name="tools" />
          <DraftActions :dirty="dirty" :saving="saving" :label="`${label} changes`" @cancel="discardOpen = true" @save="emit('save')" />
          <AdminSearch ref="field" v-model="search" :label="`Search ${label}`" />
        </div>
      </header>
      <div class="settings-body"><slot /></div>
    </section>
    <ConfirmModal v-if="discardOpen" :open="discardOpen" :title="`Discard unsaved ${label}?`" message="Your changes have not been saved." confirm-label="Discard changes"
      @confirm="answerDiscard(true, () => emit('discard'))" @close="answerDiscard(false, () => {})" />
  </PageLayout>
</template>

<style scoped>
.settings-body { display: grid; gap: 0; }
.settings-tools { flex: 1; }
@media (max-width: 767px) { .settings-tools { flex: 1 1 100%; } }
</style>
