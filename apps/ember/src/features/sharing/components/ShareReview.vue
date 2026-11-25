<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RecordDrawer } from "@citadel/ui";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import { FILE_TITLE_MAX, folderProblem, normalizeFolder } from "../../notes/api/BrainClient";
import { SKILL_LIMITS } from "../../skills/api/SkillsClient";
import { sharingClient, type Share, type ShareDetail, type ShareKind } from "../api/SharingClient";
import { isDecidedShareError, useSharingStore } from "../stores/sharing";

/** What arrived: who sent it, the text as plain text, and the three answers (keep a copy, decline, block the sender).
 * Opening it changes nothing. Render it only while a share is chosen (`v-if`). The text is another account's, so it is
 * never shown as markup and is dropped when this closes. */
const props = defineProps<{ share: Share }>();
const emit = defineEmits<{ close: []; done: [message: string, destination?: "notes" | "skills"] }>();

const KIND: Record<ShareKind, string> = { file: "File", section: "Section of a file", skill: "Skill", stack_item: "Short-term memory item" };

const store = useSharingStore();
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
const canKeep = computed(() => detail.value !== null && title.value.trim() !== "" && problem.value === "" && !busy.value);

onMounted(async () => {
  try {
    const found = await sharingClient.get(props.share.id);
    if (closed) return;
    if (found.status !== "pending") {
      decided.value = true;
      void store.load();
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
watch(() => auth.account?.id, close, { flush: "sync" });

async function answer(work: () => Promise<string>, destination?: "notes" | "skills"): Promise<void> {
  if (closed || busy.value || !detail.value) return;
  busy.value = true;
  error.value = "";
  try {
    const message = await work();
    if (!closed) {
      clear();
      emit("done", message, destination);
    }
  } catch (err) {
    if (!closed) {
      error.value = errorMessage(err);
      if (isDecidedShareError(err)) {
        decided.value = true;
        detail.value = null;
        title.value = folder.value = "";
      }
    }
  } finally {
    if (!closed) busy.value = false;
  }
}

function keep(): void {
  if (!canKeep.value) return;
  void answer(async () => {
    const landing = isSkill.value ? { title: title.value.trim() } : { title: title.value.trim(), folder: cleanFolder.value };
    await store.accept(props.share.id, landing);
    return isSkill.value
      ? "Kept as a proposed skill. Approve it on the Skills page before it is used."
      : `Kept as a file${landing.folder ? ` in ${landing.folder}` : ""}. Open it on the Notes page.`;
  }, isSkill.value ? "skills" : "notes");
}
const decline = () => answer(async () => { await store.decline(props.share.id); return "Declined."; });
const blockSender = () => answer(async () => {
  await store.block(props.share.sender);
  return `Blocked ${props.share.sender}. Their waiting shares were declined.`;
});
</script>

<template>
  <RecordDrawer :open="visible" title="Review a share" @close="close">
    <div v-if="visible" class="review">
      <p class="meta">From <strong>{{ share.sender }}</strong> · {{ KIND[share.kind] }} · {{ formatUtc(share.created_at) }}</p>
      <p v-if="loadError" class="error" role="alert">{{ loadError }}</p>
      <template v-else-if="decided">
        <p v-if="!error" role="status">This share is no longer waiting for an answer.</p>
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
        <label v-if="!isSkill" class="field"><span class="label">Keep it in folder</span><input v-model="folder" type="text" aria-label="Folder" maxlength="130" :disabled="busy" /></label>
        <p v-if="problem" class="error" role="alert">{{ problem }}</p>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="detail && !decided && !title.trim()" class="disabled-reason" role="status">Give it a title first.</p>
      <div class="buttons">
        <button type="button" class="pill-btn ghost" :disabled="busy" @click="close">Close</button>
        <template v-if="!decided">
          <button type="button" class="link-btn" :disabled="busy || !detail" @click="blockSender">Block sender</button>
          <button type="button" class="pill-btn ghost" :disabled="busy || !detail" @click="decline">Decline</button>
          <button type="button" class="pill-btn primary" :disabled="!canKeep" :aria-busy="busy" @click="keep">Keep a copy</button>
        </template>
      </div>
    </div>
  </RecordDrawer>
</template>

<style scoped>
.review .error { color: var(--text); }
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
@media (max-width: 767px) {
  .field input { min-height: 44px; font-size: max(1em, 16px); }
  .buttons button { min-height: 44px; }
}
</style>
