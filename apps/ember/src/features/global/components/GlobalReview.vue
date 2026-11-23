<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import RecordDrawer from "../../../components/ui/panel/RecordDrawer.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { FILE_TITLE_MAX, folderProblem, normalizeFolder } from "../../notes/api/BrainClient";
import { SKILL_LIMITS } from "../../skills/api/SkillsClient";
import type { Share, ShareDetail, ShareKind } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import { isDecidedShareError } from "../../sharing/stores/sharing";

/** Review another account’s share as plain text. Closing drops the preview and landing fields. */
const props = defineProps<{ share: Share }>();
const emit = defineEmits<{ close: []; done: [message: string]; decided: []; approved: [] }>();

const KIND: Record<ShareKind, string> = { file: "File", section: "Section of a file", skill: "Skill", stack_item: "Short-term memory item" };

const auth = useAuthStore();
const visible = ref(true);
const detail = ref<ShareDetail | null>(null);
const decided = ref(false);
const loadError = ref("");
const title = ref(props.share.title);
const folder = ref("shared");
const busy = ref(false);
const error = ref("");
let closed = false;

const isSkill = computed(() => props.share.kind === "skill");
const titleLimit = computed(() => isSkill.value ? SKILL_LIMITS.title : FILE_TITLE_MAX);
const cleanFolder = computed(() => normalizeFolder(folder.value));
const problem = computed(() => (isSkill.value ? "" : folderProblem(cleanFolder.value)));
const canApprove = computed(() => detail.value !== null && title.value.trim() !== "" && title.value.trim().length <= titleLimit.value && problem.value === "" && !busy.value);

onMounted(async () => {
  if (!auth.hasPermission("brain.global.write")) { close(); return; }
  try {
    const found = await globalClient.share(props.share.id);
    if (closed) return;
    if (found.status !== "pending") {
      markDecided();
      return;
    }
    detail.value = found;
    title.value = found.title;
  } catch (err) {
    if (!closed) loadError.value = errorMessage(err);
  }
});
function clear(): void {
  closed = true;
  visible.value = false;
  detail.value = null;
  title.value = folder.value = error.value = loadError.value = "";
}
function close(): void {
  if (closed) return;
  clear();
  emit("close");
}
onBeforeUnmount(clear);
watch([() => auth.account?.id, () => auth.hasPermission("brain.global.write")], close, { flush: "sync" });

function markDecided(): void {
  decided.value = true;
  detail.value = null;
  title.value = folder.value = "";
  emit("decided");
}

async function answer(work: () => Promise<unknown>, message: string, approving = false): Promise<void> {
  if (closed || busy.value || !detail.value || !auth.hasPermission("brain.global.write")) return;
  busy.value = true;
  error.value = "";
  try {
    await work();
    if (!closed) {
      clear();
      if (approving) emit("approved");
      emit("done", message);
    }
  } catch (err) {
    if (!closed) {
      if (isDecidedShareError(err)) markDecided();
      else error.value = errorMessage(err);
    }
  } finally {
    if (!closed) busy.value = false;
  }
}

function approve(): void {
  if (!canApprove.value) return;
  const landing = isSkill.value ? { title: title.value.trim() } : { title: title.value.trim(), folder: cleanFolder.value };
  void answer(() => globalClient.approve(props.share.id, landing), "Added to the global brain.", true);
}
function reject(): void {
  void answer(() => globalClient.reject(props.share.id), "Rejected.");
}
</script>

<template>
  <RecordDrawer :open="visible" title="Review a global share" @close="!busy && close()">
    <div v-if="visible" class="review">
      <p class="meta">From <strong>{{ share.sender }}</strong> · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</p>
      <p v-if="loadError" class="error" role="alert"><span class="warning" aria-hidden="true">⚠</span> {{ loadError }}</p>
      <template v-else-if="decided">
        <p v-if="!error" role="status">This share is no longer waiting for a review.</p>
      </template>
      <p v-else-if="!detail" class="muted" role="status">Loading …</p>
      <template v-else>
        <p class="untrusted" role="note">
          <svg class="line-icon" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2l6.5 11.5h-13zM8 6.5v3M8 11.5v.5" /></svg>
          {{ detail.notice }}
        </p>
        <template v-if="detail.skill">
          <h4>When to use</h4><pre class="text">{{ detail.skill.when_to_use }}</pre>
          <h4>Steps</h4><pre class="text">{{ detail.skill.steps }}</pre>
          <template v-if="detail.skill.tools"><h4>Tools</h4><pre class="text">{{ detail.skill.tools }}</pre></template>
        </template>
        <pre v-else class="text">{{ detail.body }}</pre>
        <label class="field"><span class="label">Title</span><input v-model="title" type="text" aria-label="Title" :maxlength="titleLimit" :disabled="busy" /></label>
        <label v-if="!isSkill" class="field"><span class="label">Folder</span><input v-model="folder" type="text" aria-label="Folder" :aria-invalid="!!problem" :aria-describedby="problem ? 'global-review-folder-problem' : undefined" maxlength="130" :disabled="busy" /></label>
        <p v-if="problem" id="global-review-folder-problem" class="error" role="alert"><span class="warning" aria-hidden="true">⚠</span> {{ problem }}</p>
      </template>
      <p v-if="error" class="error" role="alert"><span class="warning" aria-hidden="true">⚠</span> {{ error }}</p>
      <div class="buttons">
        <button type="button" class="pill-btn ghost" :disabled="busy" @click="close">Close</button>
        <template v-if="!decided">
          <button type="button" class="pill-btn ghost" :disabled="busy || !detail" @click="reject">Reject</button>
          <button type="button" class="pill-btn primary" :disabled="!canApprove" :aria-busy="busy" @click="approve">Add to global brain</button>
        </template>
      </div>
    </div>
  </RecordDrawer>
</template>

<style scoped>
.review .error { color: var(--text); }
.warning { color: var(--warning); }
.review { display: flex; flex-direction: column; gap: 12px; }
p, h4 { margin: 0; overflow-wrap: anywhere; }
h4 { font-size: .85em; color: var(--muted); }
.meta { font-size: .9em; color: var(--muted); }
.untrusted { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; border: 1px solid var(--warning); border-radius: var(--radius-md); font-size: .85em; }
.untrusted .line-icon { flex-shrink: 0; margin-top: 2px; color: var(--warning); }
.text { margin: 0; max-height: 40dvh; overflow: auto; scrollbar-gutter: stable; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--code-bg); font: inherit; font-size: .9em; white-space: pre-wrap; overflow-wrap: anywhere; }
.field { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: .85em; color: var(--muted); }
.field input { padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 8px; }
.field input, .buttons button { min-height: 44px; }
@media (max-width: 767px) {
  .field input { font-size: max(1em, 16px); }
}
</style>
