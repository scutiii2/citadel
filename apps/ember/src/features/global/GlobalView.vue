<script setup lang="ts">
import { PanelHelp } from "@citadel/ui";
import { computed, ref, watch } from "vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import SegmentedControl from "../../components/ui/forms/SegmentedControl.vue";
import { useAuthStore } from "../../stores/auth";
import { GLOBAL_NOTICE } from "./api/GlobalClient";
import GlobalFiles from "./components/GlobalFiles.vue";
import GlobalQueue from "./components/GlobalQueue.vue";
import GlobalSkills from "./components/GlobalSkills.vue";

type Tab = "notes" | "skills" | "queue";

const auth = useAuthStore();
const canWrite = computed(() => auth.hasPermission("brain.global.write"));
const tab = ref<Tab>("notes");
const visitedSkills = ref(false);
const fileVersion = ref(0);
const skillVersion = ref(0);
const options = computed(() => {
  const tabs: { value: Tab; label: string }[] = [
    { value: "notes", label: "Notes" },
    { value: "skills", label: "Skills" },
  ];
  if (canWrite.value) tabs.push({ value: "queue", label: "Review queue" });
  return tabs;
});

watch(() => auth.account?.id, () => {
  tab.value = "notes";
  visitedSkills.value = false;
}, { flush: "sync" });
watch(canWrite, (allowed) => {
  if (!allowed && tab.value === "queue") tab.value = "notes";
}, { flush: "sync" });
watch(tab, (section) => {
  if (section === "skills") visitedSkills.value = true;
});

function refreshApproved(destination: "notes" | "skills"): void {
  if (destination === "skills") skillVersion.value++;
  else fileVersion.value++;
}
</script>

<template>
  <PageLayout title="Global brain">
    <template #actions><PanelHelp title="Global brain">Files and skills everyone on this instance and every agent can read.</PanelHelp></template>
    <p class="notice" role="note">
      <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
      {{ GLOBAL_NOTICE }}
    </p>
    <div v-if="auth.account" :key="auth.account.id" class="sections">
      <SegmentedControl v-model="tab" :options="options" mode="tabs" id-prefix="global" aria-label="Global brain sections" />
      <section id="global-panel-notes" v-show="tab === 'notes'" role="tabpanel" aria-labelledby="global-tab-notes">
        <GlobalFiles :key="fileVersion" :can-write="canWrite" />
      </section>
      <section id="global-panel-skills" v-show="tab === 'skills'" role="tabpanel" aria-labelledby="global-tab-skills">
        <GlobalSkills v-if="visitedSkills" :key="skillVersion" :can-write="canWrite" />
      </section>
      <section v-if="canWrite" id="global-panel-queue" v-show="tab === 'queue'" role="tabpanel" aria-labelledby="global-tab-queue">
        <GlobalQueue v-if="tab === 'queue'" @added="refreshApproved" />
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.notice { display: flex; align-items: flex-start; gap: 8px; margin: 0 0 16px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); overflow-wrap: anywhere; }
.notice .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.sections { display: grid; gap: 16px; min-width: 0; justify-items: start; }
[role="tabpanel"] { width: 100%; min-width: 0; }
.sections :deep(button[role="tab"]),
.sections :deep(dialog button) { min-width: 44px; min-height: 44px; }
</style>
