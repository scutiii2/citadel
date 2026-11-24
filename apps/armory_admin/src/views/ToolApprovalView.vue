<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { toolApprovalClient } from "../api/ToolApprovalClient";
import ActionMessage from "../components/admin/ActionMessage.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";

/** The one rule Armory holds for its tools: whether every tool run waits for a person's approval. It reaches every
 * user, so a flip is a draft until Save. The rule is stored in Armory; Portcullis passes it on to each answer. */
const stored = ref(false);
const draft = ref(false);
const loading = ref(true);
const saving = ref(false);
const loadError = ref("");
const saveError = ref("");
const saved = ref(false);
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();
const changed = computed(() => draft.value !== stored.value);

async function load(): Promise<void> {
  loadError.value = "";
  loading.value = true;
  try {
    stored.value = (await toolApprovalClient.get()).force_tool_approval;
    draft.value = stored.value;
  } catch (err) {
    loadError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function flip(box: HTMLInputElement): void {
  draft.value = box.checked;
  saved.value = false;
  saveError.value = "";
}

async function save(): Promise<void> {
  if (!changed.value || saving.value) return;
  const on = draft.value;
  saving.value = true;
  saveError.value = "";
  await panel.value?.keepFocus(async () => {
    try {
      stored.value = (await toolApprovalClient.set(on)).force_tool_approval;
      draft.value = stored.value;
      saved.value = true;
    } catch (err) {
      // The draft stays, so Save can be retried or Cancel drops it.
      saveError.value = errorMessage(err);
    } finally {
      saving.value = false;
    }
  });
}

function discard(): void {
  draft.value = stored.value;
  saveError.value = "";
}

onMounted(load);
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Tool approval" heading="Tool approval" label="tool approval" :dirty="changed" :saving="saving" @save="save" @discard="discard">
    <template #help>
      <p>Chooses whether tool actions need a person's approval before they run. Edit, then Save to apply to every user.</p>
      <p>Armory holds the tools, so it keeps this rule. Chat reads it before each answer.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <ActionMessage v-else-if="loadError" kind="error" :text="loadError" class="note">
      <button type="button" class="link-btn" @click="load">Retry</button>
    </ActionMessage>
    <section v-else v-show="panel?.matches('Approval', 'Require approval for every tool', 'Allow once', 'Typed commands')" class="group" aria-labelledby="approval-title" data-test="group">
      <h3 id="approval-title">Approval</h3>
      <p class="lede">Applies to all users.</p>
      <div class="switch-row">
        <ToggleSwitch :checked="draft" :disabled="saving" data-test="force" @change="flip($event.target as HTMLInputElement)">Require approval for every tool</ToggleSwitch>
        <FieldLabel bare title="Require approval for every tool">
          <p><b>On:</b> every tool the agent wants to run waits for the user's own "Allow once". "Allow for this chat" is not offered, whatever the user chose.</p>
          <p><b>Off:</b> each user decides for themselves, per chat.</p>
          <p>Typed commands such as /tool are never held: the person types the exact command themselves.</p>
        </FieldLabel>
      </div>
      <p v-if="changed" class="unsaved" role="status" data-test="unsaved">You have an unsaved change. Turning it {{ draft ? "on" : "off" }} applies to every user.</p>
      <ActionMessage v-if="saveError" kind="error" :text="saveError" />
      <ActionMessage v-else-if="saved && !changed" kind="ok" text="Saved. The next answer uses it." data-test="notice" />
    </section>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.muted { color: var(--muted); }
.group { display: grid; gap: 12px; max-width: 720px; padding: 16px; }
.group h3 { margin: 0; font-size: 1em; }
.lede { margin: 0; color: var(--muted); font-size: 0.9em; }
.switch-row { display: flex; align-items: center; gap: 4px; }
.unsaved { margin: 0; font-size: 0.9em; }
</style>
