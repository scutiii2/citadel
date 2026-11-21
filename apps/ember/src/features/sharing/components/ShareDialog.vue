<script lang="ts">
export type ShareTarget =
  | { kind: "file"; fileId: string; label: string; headings: string[] }
  | { kind: "skill"; skillId: number; label: string }
  | { kind: "stack_item"; chatId: string; itemId: number; label: string };
</script>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { SHARE_NAME_MAX, type NewShare, type Recipient, type Share } from "../api/SharingClient";
import { useSharingStore } from "../stores/sharing";

/** Send a copy of one thing to another account or to the global brain. Nothing is sent until Send is pressed. The
 * recipient (or, for the global brain, a reviewer) decides whether to keep it; the sender can withdraw it until then.
 * Render this only while there is a target (`v-if`): it needs the sharing store. */
const props = defineProps<{ open: boolean; target: ShareTarget | null }>();
const emit = defineEmits<{ close: [] }>();

const store = useSharingStore();
const auth = useAuthStore();
const dismissed = ref(false);
const visible = computed(() => props.open && !dismissed.value);
const mode = ref<"account" | "global">("account");
const username = ref("");
const what = ref<"file" | "section">("file");
const heading = ref("");
const sending = ref(false);
const error = ref("");
const done = ref<Share | null>(null);
let run = 0; // an answer that arrives after the dialog was closed or reopened is dropped

function reset(): void {
  run++;
  mode.value = "account";
  username.value = "";
  what.value = "file";
  heading.value = props.target?.kind === "file" ? (props.target.headings[0] ?? "") : "";
  sending.value = false;
  error.value = "";
  done.value = null;
}
function close(): void {
  dismissed.value = true;
  reset();
  heading.value = "";
  emit("close");
}
watch(() => props.open, (isOpen) => {
  dismissed.value = !isOpen;
  reset();
  if (!isOpen) heading.value = "";
}, { immediate: true, flush: "sync" });
watch(() => props.target, () => { if (visible.value) reset(); }, { flush: "sync" });
watch(() => auth.account?.id, close, { flush: "sync" });
onBeforeUnmount(() => { run++; });

const headings = computed(() => (props.target?.kind === "file" ? props.target.headings : []));
const valid = computed(() => mode.value === "global" || username.value.trim() !== "");

function request(): NewShare | null {
  const target = props.target;
  if (!target) return null;
  const to: Recipient = mode.value === "global" ? { to_global: true } : { recipient: username.value.trim() };
  if (target.kind === "file") {
    return what.value === "section" && heading.value
      ? { kind: "section", file_id: target.fileId, heading: heading.value, ...to }
      : { kind: "file", file_id: target.fileId, ...to };
  }
  if (target.kind === "skill") return { kind: "skill", skill_id: target.skillId, ...to };
  return { kind: "stack_item", chat_id: target.chatId, item_id: target.itemId, ...to };
}

async function send(): Promise<void> {
  const share = request();
  if (!visible.value || !share || !valid.value || sending.value) return;
  const mine = run;
  sending.value = true;
  error.value = "";
  try {
    const made = await store.create(share);
    if (mine === run) done.value = made;
  } catch (err) {
    if (mine === run) error.value = errorMessage(err);
  } finally {
    if (mine === run) sending.value = false;
  }
}
</script>

<template>
  <BaseModal :open="visible" title="Share a copy" @close="close">
    <template v-if="visible && target">
      <div v-if="done" class="result" role="status">
        <p v-if="mode === 'global'">Sent to the global brain review queue. A reviewer decides; if it is approved, every account and its agents can read it. You can withdraw it from Shares until then.</p>
        <p v-else>Sent to {{ done.recipient }}. They can keep or decline it. You can withdraw it from Shares until they answer.</p>
        <div class="buttons"><button type="button" class="pill-btn primary" @click="close">Close</button></div>
      </div>
      <form v-else class="share-form" @submit.prevent="send">
        <p>You are sharing a copy of <strong>{{ target.label }}</strong>. Later changes to the original are not sent.</p>
        <fieldset v-if="headings.length" class="group" :disabled="sending">
          <legend>What to share</legend>
          <label><input v-model="what" type="radio" name="what" value="file" /> Whole file</label>
          <label><input v-model="what" type="radio" name="what" value="section" /> One section</label>
          <select v-if="what === 'section'" v-model="heading" aria-label="Section">
            <option v-for="name in headings" :key="name" :value="name">{{ name }}</option>
          </select>
        </fieldset>
        <fieldset class="group" :disabled="sending">
          <legend>Who gets it</legend>
          <label><input v-model="mode" type="radio" name="who" value="account" /> Another account</label>
          <input v-if="mode === 'account'" v-model="username" type="text" aria-label="Username" placeholder="Their username" :maxlength="SHARE_NAME_MAX" autocomplete="off" />
          <label><input v-model="mode" type="radio" name="who" value="global" /> The global brain</label>
        </fieldset>
        <p v-if="mode === 'global'" class="note" role="note">Global shares are reviewed first. If approved, every account and every agent can read the text. Do not share private data.</p>
        <p v-else class="note" role="note">They see the text and choose whether to keep it. Tags and links to your private files are removed. You can withdraw it from Shares until they answer.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="buttons">
          <button type="button" class="pill-btn ghost" :disabled="sending" @click="close">Cancel</button>
          <button type="submit" class="pill-btn primary" :disabled="!valid || sending" :aria-busy="sending">Send</button>
        </div>
      </form>
    </template>
  </BaseModal>
</template>

<style scoped>
.share-form, .result { display: flex; flex-direction: column; gap: 14px; }
.share-form .error { color: var(--text); }
p { margin: 0; overflow-wrap: anywhere; }
.group { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.group legend { padding: 0 6px; font-size: .85em; color: var(--muted); }
.group label { display: flex; align-items: center; gap: 8px; }
.group input[type="text"], .group select { width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; }
.note { font-size: .85em; color: var(--muted); }
.buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
@media (max-width: 767px) {
  .group label, .buttons button { min-height: 44px; }
  .group input[type="text"], .group select { min-height: 44px; font-size: max(1em, 16px); }
}
</style>
