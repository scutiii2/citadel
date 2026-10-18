<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { ForgeCreatedWorker, ForgeMode, ForgeProvider, ForgeWorker } from "../api/ForgeClient";
import ConfirmModal from "../components/ConfirmModal.vue";
import ForgeComposer from "../components/ForgeComposer.vue";
import ForgeGroupList from "../components/ForgeGroupList.vue";
import ForgeInviteModal from "../components/ForgeInviteModal.vue";
import ForgeMembersPanel from "../components/ForgeMembersPanel.vue";
import ForgeNewGroupModal from "../components/ForgeNewGroupModal.vue";
import ForgeTranscript from "../components/ForgeTranscript.vue";
import ForgeWorkersModal from "../components/ForgeWorkersModal.vue";
import PageLayout from "../components/PageLayout.vue";
import { useAuthStore } from "../stores/auth";
import { useForgeStore } from "../stores/forge";
import { errorMessage } from "../utils/errors";
import { FULL_AUTO_PHRASE } from "../utils/forgeModes";

const REFRESH_MS = 10_000;

const forge = useForgeStore();
const auth = useAuthStore();

const draft = ref("");
const sending = ref(false);
const sendError = ref("");
const panelBusy = ref(false);
const panelError = ref("");

type Dialog = "" | "new" | "invite" | "workers" | "full-auto" | "delete-group" | "remove-worker";
const dialog = ref<Dialog>("");
const dialogBusy = ref(false);
const dialogError = ref("");
const createdWorker = ref<ForgeCreatedWorker | null>(null);
const workerToRemove = ref<ForgeWorker | null>(null);

const group = computed(() => forge.selected);
const labels = computed(() => group.value?.members.map((m) => m.label) ?? []);
const canEditPlans = computed(() => auth.hasPermission("settings.manage"));
const disabledReason = computed(() => (group.value && group.value.members.length === 0 ? "Invite a worker first." : ""));
const running = computed(() => forge.transcript.running);

let timer: ReturnType<typeof setInterval> | undefined;
onMounted(async () => {
  await forge.ensureLoaded();
  if (forge.selectedId !== null) forge.reconnect();
  timer = setInterval(() => void forge.refresh(), REFRESH_MS);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  forge.leave();
});

watch(
  () => forge.selectedId,
  () => {
    draft.value = "";
    sendError.value = "";
    panelError.value = "";
  },
);

function open(next: Dialog): void {
  dialogError.value = "";
  dialog.value = next;
}
function close(): void {
  if (dialogBusy.value) return;
  dialog.value = "";
  workerToRemove.value = null;
}

/** Runs a dialog's action: busy while it runs, closed when it succeeds, its error shown when it fails. */
async function runInDialog(action: () => Promise<void>, closeAfter = true): Promise<void> {
  dialogBusy.value = true;
  dialogError.value = "";
  try {
    await action();
    if (closeAfter) dialog.value = "";
  } catch (err) {
    dialogError.value = errorMessage(err);
  } finally {
    dialogBusy.value = false;
  }
}

/** Runs a change made from the side panel: its error shows under the panel, the page stays usable. */
async function runInPanel(action: () => Promise<unknown>): Promise<void> {
  panelBusy.value = true;
  panelError.value = "";
  try {
    await action();
  } catch (err) {
    panelError.value = errorMessage(err);
  } finally {
    panelBusy.value = false;
  }
}

async function send(): Promise<void> {
  if (sending.value) return;
  sending.value = true;
  sendError.value = "";
  try {
    await forge.send(draft.value.trim());
    draft.value = "";
  } catch (err) {
    sendError.value = errorMessage(err);
  } finally {
    sending.value = false;
  }
}

async function stop(): Promise<void> {
  try {
    await forge.stop();
  } catch (err) {
    sendError.value = errorMessage(err);
  }
}

async function answer(requestId: string, allow: boolean): Promise<void> {
  try {
    await forge.answer(requestId, allow);
  } catch (err) {
    sendError.value = errorMessage(err);
  }
}

const setMode = (mode: ForgeMode) => runInPanel(() => forge.updateGroup(group.value!.id, { mode }));
const setRelay = (relay: boolean) => runInPanel(() => forge.updateGroup(group.value!.id, { relay }));
const setFolder = (workerId: number, folder: string) => runInPanel(() => forge.setFolder(group.value!.id, workerId, folder));
const browseFolder = (workerId: number, start: string) => forge.browseFolder(workerId, start);
const removeMember = (workerId: number) => runInPanel(() => forge.removeMember(group.value!.id, workerId));

const createGroup = (title: string, mode: Exclude<ForgeMode, "full_auto">) => runInDialog(() => forge.createGroup(title, mode).then(() => undefined));
const invite = (workerId: number, folder: string) => runInDialog(() => forge.invite(group.value!.id, workerId, folder));
const confirmFullAuto = () =>
  runInDialog(() => forge.updateGroup(group.value!.id, { mode: "full_auto", confirm_full_auto: true }).then(() => undefined));
const deleteGroup = () => runInDialog(() => forge.removeGroup(group.value!.id));

async function createWorker(provider: ForgeProvider, label: string): Promise<void> {
  await runInDialog(async () => {
    createdWorker.value = await forge.createWorker(provider, label);
  }, false);
}

function askRemoveWorker(worker: ForgeWorker): void {
  workerToRemove.value = worker;
  open("remove-worker");
}

async function removeWorker(): Promise<void> {
  const worker = workerToRemove.value;
  if (!worker) return;
  await runInDialog(async () => {
    await forge.removeWorker(worker.id);
    workerToRemove.value = null;
  });
  if (!dialogError.value) open("workers");
}

const savePlans = (provider: ForgeProvider, plans: string[]) => runInDialog(() => forge.savePlans(provider, plans), false);

function dismissToken(): void {
  createdWorker.value = null;
}
</script>

<template>
  <PageLayout title="Forge" description="Talk to your own Claude and Codex workers and let them work on your computer." wide fill>
    <template #actions>
      <button type="button" class="workers-button" @click="open('workers')">Workers</button>
    </template>

    <p v-if="forge.loadError" class="banner error" role="alert">
      {{ forge.loadError }} <button type="button" class="link" @click="forge.refresh()">Try again</button>
    </p>

    <div v-if="forge.loading" class="loading" aria-busy="true">Loading…</div>

    <div v-else-if="!forge.workers.length && !forge.groups.length" class="guide">
      <h3>Add a worker to begin</h3>
      <p>
        A worker is your own Claude Code or Codex, running on your computer with your own login. Forge talks to it through a
        small program, <code>ember_worker</code>, that connects out to Ember. Nothing is shared with anyone else.
      </p>
      <button type="button" class="primary" @click="open('workers')">Add a worker</button>
    </div>

    <div v-else class="workspace">
      <ForgeGroupList class="side-left" :groups="forge.groups" :selected-id="forge.selectedId" @select="forge.select($event)" @create="open('new')" />

      <section class="chat" aria-label="Conversation">
        <div v-if="!group" class="placeholder">
          <h3>{{ forge.groups.length ? "Choose a group" : "Create your first group" }}</h3>
          <p>A group is a chat between you and the workers you invite, each working in a folder on its own computer.</p>
          <button v-if="!forge.groups.length" type="button" class="primary" @click="open('new')">New group</button>
        </div>

        <template v-else>
          <header class="chat-head">
            <h3>{{ group.title }}</h3>
            <span v-if="running" class="working">
              <svg class="spinner" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>
              Working
            </span>
          </header>
          <p v-if="forge.connection === 'lost'" class="banner error" role="alert">
            Connection lost. <button type="button" class="link" @click="forge.reconnect()">Reconnect</button>
          </p>
          <ForgeTranscript :items="forge.transcript.items" :running="running" @answer="answer" />
          <ForgeComposer
            v-model="draft"
            :labels="labels"
            :running="running"
            :busy="sending"
            :disabled-reason="disabledReason"
            :error="sendError"
            @send="send"
            @stop="stop"
          />
        </template>
      </section>

      <div v-if="group" class="side-right">
        <ForgeMembersPanel
          :group="group"
          :busy="panelBusy"
          @mode="setMode"
          @full-auto="open('full-auto')"
          @relay="setRelay"
          @invite="open('invite')"
          :browse="browseFolder"
          @folder="setFolder"
          @remove="removeMember"
          @delete="open('delete-group')"
        />
        <p v-if="panelError" class="banner error" role="alert">{{ panelError }}</p>
      </div>
    </div>

    <ForgeNewGroupModal :open="dialog === 'new'" :busy="dialogBusy" :error="dialogError" @close="close" @create="createGroup" />
    <ForgeInviteModal :open="dialog === 'invite'" :group="group" :workers="forge.workers" :busy="dialogBusy" :error="dialogError" :browse="browseFolder" @close="close" @invite="invite" />
    <ForgeWorkersModal
      :open="dialog === 'workers'"
      :workers="forge.workers"
      :plans="forge.plans"
      :can-edit-plans="canEditPlans"
      :busy="dialogBusy"
      :error="dialogError"
      :created="createdWorker"
      @close="close"
      @create="createWorker"
      @remove="askRemoveWorker"
      @save-plans="savePlans"
      @dismiss-token="dismissToken"
    />
    <ConfirmModal
      :open="dialog === 'full-auto'"
      title="Switch to full auto?"
      message="Workers will run any tool, including commands that change or delete files, without asking you. Only do this in a folder you can afford to lose."
      confirm-label="Switch to full auto"
      danger
      :require-text="FULL_AUTO_PHRASE"
      :busy="dialogBusy"
      @confirm="confirmFullAuto"
      @close="close"
    />
    <ConfirmModal
      :open="dialog === 'delete-group'"
      title="Delete this group?"
      message="Its whole conversation is deleted. The workers and your files are not touched."
      confirm-label="Delete group"
      danger
      :require-text="group?.title ?? ''"
      :busy="dialogBusy"
      @confirm="deleteGroup"
      @close="close"
    />
    <ConfirmModal
      :open="dialog === 'remove-worker'"
      title="Remove this worker?"
      message="Its pairing token stops working and it leaves every group. Pair it again later with a new worker."
      confirm-label="Remove worker"
      danger
      :require-text="workerToRemove?.label ?? ''"
      :busy="dialogBusy"
      @confirm="removeWorker"
      @close="close"
    />
    <p v-if="dialog === 'delete-group' || dialog === 'full-auto' || dialog === 'remove-worker'" class="sr-only" role="alert">{{ dialogError }}</p>
  </PageLayout>
</template>

<style scoped>
.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 260px;
  gap: 16px;
}
.side-left,
.side-right {
  min-height: 0;
  overflow-y: auto;
}
.chat {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
}
.chat-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.chat-head h3 {
  margin: 0;
  font-size: 1em;
  overflow-wrap: anywhere;
}
.working {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 0.85em;
}
.spinner {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2.4;
  stroke-linecap: round;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.guide,
.placeholder {
  margin: auto;
  max-width: 520px;
  padding: 24px 16px;
  text-align: center;
}
.guide h3,
.placeholder h3 {
  margin: 0 0 8px;
}
.guide p,
.placeholder p {
  color: var(--muted);
}
.guide code {
  background: var(--code-bg);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
  font-family: var(--mono);
}
.loading {
  color: var(--muted);
}
.banner {
  margin: 0 0 8px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
}
.banner.error {
  border-color: var(--danger);
  color: var(--danger);
}
button.link {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-decoration: underline;
  cursor: pointer;
}
button.primary,
.workers-button {
  border-radius: var(--radius-full);
  padding: 8px 18px;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
button.primary {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--accent-contrast);
}
.workers-button {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
}
.workers-button:hover {
  border-color: var(--accent);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: minmax(0, 1fr);
    overflow-y: auto;
  }
  .chat {
    min-height: 60vh;
  }
}
</style>
