<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from "vue";
import EmberLogo from "../../../components/layout/EmberLogo.vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import ChatHeader from "../components/ChatHeader.vue";
import ChatInput from "../components/ChatInput.vue";
import ApprovalModePicker from "../components/ApprovalModePicker.vue";
import ChatSettingsMenu from "../components/ChatSettingsMenu.vue";
import CommandFormModal from "../../../components/tools/forms/CommandFormModal.vue";
import ElapsedTime from "../../../components/ui/status/ElapsedTime.vue";
import ConversationSidebar from "../components/ConversationSidebar.vue";
import FolderDialogs from "../components/FolderDialogs.vue";
import MessageList from "../components/MessageList.vue";
import ShareDialog from "../components/ShareDialog.vue";
import TemplatesModal from "../components/TemplatesModal.vue";
import TriageQuestionModal from "../components/TriageQuestionModal.vue";
import TurnNotices from "../components/TurnNotices.vue";
import { useEntryAgentStore } from "../stores/entryAgent";
import { useAuthStore } from "../../../stores/auth";
import { useChatStore } from "../stores/chat";
import { useFoldersStore } from "../stores/folders";
import { useChatTemplates } from "../composables/useChatTemplates";
import type { CommandInfo } from "../../../api/tools/CommandsClient";
import type { ChatFolder } from "../api/FoldersClient";
import type { JsonSchema } from "../../../api/types";
import { useChatRoute } from "../composables/useChatRoute";
import { useChatShortcuts } from "../composables/useChatShortcuts";
import { useFolderCollapse } from "../composables/useFolderCollapse";
import { useSidebarCollapse } from "../composables/useSidebarCollapse";
import { agentLabelFor } from "../utils/agentLabels";
import { builtinCommand, type BuiltinCommand } from "../utils/builtinCommands";
import { questionHistory } from "../../../utils/content/attachments";
import { conversationToMarkdown } from "../utils/chatExport";
import { downloadText, exportFileName } from "../../../utils/browser/textDownload";
import { errorMessage } from "../../../utils/errors";

const auth = useAuthStore();
const chat = useChatStore();
// storeToRefs keeps destructured state reactive; actions come off `chat`.
const {
  sortedConversations,
  activeId,
  active,
  messages,
  streaming,
  activity,
  liveUsage,
  liveTokens,
  liveSteps,
  livePlans,
  busy,
  caveman,
  independent,
  secondBrainAvailable,
  secondBrainScope,
  saveToSecondBrain,
  secondBrainPending,
  plan,
  planLean,
  listLoading,
  listReady,
  chatLoading,
  loadError,
  saveError,
  sendError,
  notices,
  working,
  contextUsage,
  contextParts,
  contextExact,
  contextAgentUsage,
  contextPanel,
  contextAccuracy,
  commands,
  enabledExtensions,
  approvalMode,
  askBeforeTools,
  forceToolApproval,
  chime,
  suggestion,
  clockStart,
  allowedTools,
  pendingApprovals,
  deciding,
  pendingQuestions,
  answeringQuestions,
  searchQuery,
  searchActive,
  searchHits,
  searching,
  searchError,
} = storeToRefs(chat);
onMounted(() => void chat.loadCommands());
onActivated(() => void chat.refreshSecondBrainAvailability());

// Chat folders: the list, which of them are folded, and the new / rename /
// delete dialogs the sidebar's menus open.
const folderStore = useFoldersStore();
const folderCollapse = useFolderCollapse();
const folderMoveError = ref("");
async function moveFolder(folder: ChatFolder, direction: "up" | "down"): Promise<void> {
  folderMoveError.value = "";
  try {
    await folderStore.move(folder.id, direction);
  } catch (error) {
    folderMoveError.value = errorMessage(error);
  }
}
const folderDialogs = ref<InstanceType<typeof FolderDialogs> | null>(null);
onMounted(() => void folderStore.ensureLoaded());

/** Every chat filed in the folder, pinned ones included: deleting it deletes them all. */
function chatsIn(folder: ChatFolder): number {
  return sortedConversations.value.filter((c) => c.folderId === folder.id).length;
}

/** "Move to > New folder...": make the folder, then put the chat in it. */
function moveToNewFolder(chatId: string): void {
  folderDialogs.value?.openCreate((folder) => chat.setChatFolder(chatId, folder.id));
}

const entryAgent = useEntryAgentStore();
const agentLabels = computed(() => entryAgent.labels);
const { templates, templatesOpen, templatesDraft, savedPrompts, openTemplates, saveAsPrompt } =
  useChatTemplates(() => messages.value);
const shareOpen = ref(false);

// The command form: opened when a command with parameters is picked from
// the input's suggestions. Submitting runs the command it builds.
const formCommand = ref<CommandInfo | null>(null);
const formSchema = ref<JsonSchema | null>(null);
const input = ref<InstanceType<typeof ChatInput> | null>(null);
const triageOpen = ref(false);

async function openCommandForm(command: CommandInfo): Promise<void> {
  const schema = await chat.commandSchema(command);
  if (!schema) return; // no parameters: the typed command runs as it is
  formSchema.value = schema;
  formCommand.value = command;
}

function closeCommandForm(): void {
  formCommand.value = null;
  formSchema.value = null;
}

/** A question ember_api did not take (no entry agent, limit reached ...) goes
 * back into the box, as typed, along with its files. */
async function onSend(question: string): Promise<void> {
  const builtin = builtinCommand(question);
  if (builtin) {
    if (!runBuiltin(builtin)) input.value?.restore(question);
    return;
  }
  if (!(await chat.send(question))) input.value?.restore(question);
}

/** /clear, /compact, /export and /share: the same as the buttons in the chat
 * header, with the same confirms and the same rules. False when refused (an
 * error says why), so the typed text is given back. */
function runBuiltin(command: BuiltinCommand): boolean {
  if (!active.value || messages.value.length === 0) {
    sendError.value = `/${command}: this chat has no messages yet.`;
    return false;
  }
  if ((command === "clear" || command === "compact") && (busy.value || working.value)) {
    sendError.value = `/${command}: wait for the current answer to finish.`;
    return false;
  }
  if (command === "share" && !auth.hasPermission("chat.share")) {
    sendError.value = "Sharing needs the chat.share permission.";
    return false;
  }
  sendError.value = "";
  if (command === "clear") clearActive();
  else if (command === "compact") summarizeActive();
  else if (command === "export") exportActive();
  else shareOpen.value = true;
  return true;
}

function runCommandForm(text: string): void {
  closeCommandForm();
  // An answer is still being written: leave the command ready to send.
  if (busy.value) {
    input.value?.setDraft(text);
    return;
  }
  input.value?.setDraft("");
  void chat.send(text);
}

// Narrow screens only: the sidebar is a drawer toggled by the menu button.
const drawerOpen = ref(false);
const historyButton = ref<HTMLButtonElement | null>(null);
const closeHistoryButton = ref<HTMLButtonElement | null>(null);
watch(drawerOpen, async (open) => {
  await nextTick();
  if (open) closeHistoryButton.value?.focus({ preventScroll: true });
  else if (shown.value) historyButton.value?.focus({ preventScroll: true });
});
// Wider screens: the list can be folded away to give the chat the room.
const { collapsed: sidebarCollapsed, toggle: toggleSidebar } = useSidebarCollapse();

// The address bar follows the open chat (/chat/<id>) and the other way round.
// The page is cached behind the other pages (KeepAlive): while it is, the
// address belongs to them.
const shown = ref(false);
const route = useChatRoute(
  {
    activeId,
    listReady,
    hasChat: chat.hasChat,
    selectChat: chat.selectChat,
    newChat: chat.newChat,
    reload: chat.reload,
  },
  shown,
);
const { notFound } = route;
onActivated(() => {
  shown.value = true;
  route.activate();
});
onDeactivated(() => {
  shown.value = false;
  drawerOpen.value = false;
});

function onNew(): void {
  route.startNew();
  drawerOpen.value = false;
}

function exportActive(): void {
  const conversation = active.value;
  if (!conversation) return;
  const agentLabel = agentLabelFor(conversation.agentId, entryAgent.labels) ?? null;
  downloadText(
    exportFileName(conversation.title, "md"),
    conversationToMarkdown(conversation, agentLabel),
    "text/markdown",
  );
}

// Clear and compact ask first, in the confirmation dialog.
const pendingChatAction = ref<"clear" | "compact" | null>(null);

const chatActionCopy = computed(() => {
  if (pendingChatAction.value === "clear") {
    return {
      title: "Start afresh",
      message: `Start "${active.value?.title ?? ""}" afresh? The agent forgets the earlier messages; they stay readable as a collapsed log.`,
      label: "Start afresh",
    };
  }
  return {
    title: "Condense messages",
    message:
      "Condense the earlier messages into a summary? The agent keeps only the summary from now on; the messages stay readable as a collapsed log.",
    label: "Condense",
  };
});

function clearActive(): void {
  if (active.value) pendingChatAction.value = "clear";
}

function summarizeActive(): void {
  if (active.value) pendingChatAction.value = "compact";
}

function runChatAction(): void {
  const action = pendingChatAction.value;
  pendingChatAction.value = null;
  if (action === "clear") void chat.clearChat();
  else if (action === "compact") void chat.summarizeChat();
}

// Share of the agent's context the last answer used; worth watching past
// about half, since ember_api summarizes automatically at 60%.
const contextPercent = computed(() => {
  const usage = contextUsage.value;
  return usage ? Math.min(100, Math.round((usage.tokens / usage.window) * 100)) : null;
});

// What fills that context, for the panel the meter opens: only when the setting
// is on and the last answer says (older answers do not).
const contextBreakdown = computed(() => {
  const usage = contextUsage.value;
  if (!contextPanel.value) return null;
  if ((!usage || contextParts.value.length === 0) && contextAgentUsage.value.length === 0) return null;
  return { tokens: usage?.tokens ?? 0, window: usage?.window ?? 0, parts: contextParts.value, exact: contextExact.value, agentUsage: contextAgentUsage.value };
});

function onSelect(id: string, messageIndex?: number): void {
  route.open(id, { messageIndex });
  drawerOpen.value = false;
}

// Tools the user allowed for the open chat ("Allow for this chat").
const allowedCount = computed(() => (activeId.value ? (allowedTools.value[activeId.value]?.length ?? 0) : 0));

// What ↑ and ↓ in the input walk through: what was typed in this chat.
const history = computed(() => questionHistory(messages.value));

useChatShortcuts({
  canStop: () => busy.value,
  stop: () => void chat.stop(),
  focusInput: () => input.value?.focus(),
  newChat: onNew,
});
</script>

<template>
  <section class="chat-view">
    <ConversationSidebar
      id="chat-history"
      aria-label="Conversations"
      @keydown.esc.stop="drawerOpen = false"
      :class="['sidebar', { open: drawerOpen, collapsed: sidebarCollapsed }]"
      :conversations="sortedConversations"
      :active-id="activeId"
      :locked="false"
      :loading="listLoading"
      :busy="busy"
      :query="searchQuery"
      :search-active="searchActive"
      :hits="searchHits"
      :searching="searching"
      :search-error="searchError"
      @search="chat.setSearch"
      @new="onNew"
      @select="onSelect"
      @delete="chat.deleteChat"
      @rename="chat.renameChat"
      @delete-all="chat.deleteAllChats"
      @delete-many="chat.deleteChats"
      :folders="folderStore.folders"
      :folder-error="folderStore.loadError"
      :folder-move-error="folderMoveError"
      :folders-moving="folderStore.moving"
      @move-folder="moveFolder"
      :collapsed-folders="folderCollapse.collapsed.value"
      @pin="chat.setChatPinned"
      @move="chat.setChatFolder"
      @move-new="moveToNewFolder"
      @toggle-folder="folderCollapse.toggle"
      @new-folder="folderDialogs?.openCreate()"
      @retry-folders="folderStore.reload()"
      @rename-folder="(f: ChatFolder) => folderDialogs?.openRename(f)"
      @delete-folder="(f: ChatFolder) => folderDialogs?.openDelete(f, chatsIn(f))"
    >
      <template #header>
        <div class="sheet-heading">
          <h2>Conversations</h2>
          <button ref="closeHistoryButton" type="button" aria-label="Close conversations" @click="drawerOpen = false">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg>
          </button>
        </div>
      </template>
    </ConversationSidebar>
    <FolderDialogs ref="folderDialogs" />
    <div v-if="drawerOpen" class="backdrop" @click="drawerOpen = false" />
    <button
      type="button"
      :class="['collapse', { collapsed: sidebarCollapsed }]"
      :title="sidebarCollapsed ? 'Show chat list' : 'Hide chat list'"
      :aria-label="sidebarCollapsed ? 'Show chat list' : 'Hide chat list'"
      :aria-expanded="!sidebarCollapsed"
      @click="toggleSidebar"
    >
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
        <path :d="sidebarCollapsed ? 'M9 5l7 7-7 7' : 'M15 5l-7 7 7 7'" />
      </svg>
    </button>

    <div class="main">
      <div class="mobile-header">
      <button ref="historyButton" type="button" class="menu" title="Chats" aria-label="Chats" aria-controls="chat-history" :aria-expanded="drawerOpen" @click="drawerOpen = !drawerOpen">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
      <span class="mobile-brand"><EmberLogo /> <strong>ember</strong></span>
      <button type="button" class="new-mobile-chat" aria-label="New chat" title="New chat" @click="onNew">
        <svg viewBox="0 0 24 24" width="21" height="21" aria-hidden="true"><path d="M12 5H5v14h14v-7M14 4l6 6M10 14l2-6 6-6 4 4-6 6z" /></svg>
      </button>
      </div>
      <ChatHeader
        :title="active?.title ?? 'New chat'"
        :has-messages="!!active && messages.length > 0"
        :context-percent="contextPercent"
        :breakdown="contextBreakdown"
        :accuracy="contextAccuracy"
        @update:accuracy="chat.setContextAccuracy"
        :locked="busy || !!working"
        @export="exportActive"
        @share="shareOpen = true"
        @summarize="summarizeActive"
        @clear="clearActive"
      />
      <div v-if="saveError || loadError" class="banner" role="alert">
        <template v-if="saveError">
          Couldn't save your chats: {{ saveError }}
          <button type="button" @click="chat.retrySave()">Retry</button>
        </template>
        <template v-else>
          Couldn't load chats: {{ loadError }}
          <button type="button" @click="chat.reload()">Retry</button>
        </template>
      </div>
      <div v-if="notFound" class="banner" role="alert">
        That chat doesn't exist, or it was deleted.
        <button type="button" @click="notFound = false">Dismiss</button>
      </div>
      <div v-if="sendError" class="banner" role="alert">
        {{ sendError }}
        <button type="button" @click="sendError = ''">Dismiss</button>
      </div>
      <TurnNotices :notices="notices" @dismiss="chat.dismissNotices()" />
      <p v-if="chatLoading" class="loading">Loading chat …</p>
      <MessageList
        v-show="!chatLoading"
        class="messages"
        :conversation-id="active?.id ?? null"
        :draft-scope="auth.account?.id ?? null"
        :messages="messages"
        :streaming="streaming"
        :activity="activity"
        :live-tokens="liveTokens ? liveUsage : null"
        :steps="liveSteps"
        :plans="livePlans"
        :busy="busy"
        :can-change="!busy && !working"
        :approvals="pendingApprovals"
        :since="clockStart"
        :commands="commands"
        :agent-labels="agentLabels"
        :deciding="deciding"
        :questions="pendingQuestions"
        :answering-questions="answeringQuestions"
        :approval-required="forceToolApproval"
        :saved-prompts="savedPrompts"
        @save-prompt="saveAsPrompt"
        @decide="chat.decideApproval"
        @answer-question="chat.answerQuestion"
        @skip-question="chat.skipQuestion"
        :regenerate-index="chat.regenerateIndex"
        :jump-index="chat.jumpIndex"
        @jumped="chat.clearJump"
        @regenerate="chat.regenerate"
        @branch="chat.branchFrom"
        @edit="chat.editAndResend"
      />
      <div class="composer-area">
        <ChatInput
          ref="input"
          :busy="busy"
          :commands="commands"
          :history="history"
          :suggestion="suggestion"
          :independent="independent"
          @update:independent="chat.setIndependent"
          :schema-for="chat.commandSchema"
          :templates="templates.templates"
          :templates-loading="templates.loading"
          :templates-error="templates.loadError"
          @templates-needed="templates.ensureLoaded()"
          @manage-templates="openTemplates"
          @send="onSend"
          @stop="chat.stop"
          @form="openCommandForm"
          @triage="triageOpen = true"
          @suggestion-used="chat.clearSuggestion"
        >
          <template #tools>
            <ChatSettingsMenu
              :caveman="caveman"
              :independent="independent"
              :second-brain-scope="secondBrainScope"
              @update:second-brain-scope="chat.setSecondBrainScope"
              :second-brain-available="secondBrainAvailable"
              :save-to-second-brain="saveToSecondBrain"
              :second-brain-pending="secondBrainPending"
              @update:save-to-second-brain="chat.setSaveToSecondBrain"
              :plan="plan"
              :plan-lean="planLean"
              :ask-before-tools="askBeforeTools"
              :force-tool-approval="forceToolApproval"
              :chime="chime"
              :allowed-count="allowedCount"
              :enabled-extensions="enabledExtensions"
              :attention="pendingApprovals.length > 0"
              @update:caveman="chat.setCaveman"
              @update:independent="chat.setIndependent"
              @update:plan="chat.setPlan"
              @update:plan-lean="chat.setPlanLean"
              @update:chime="chat.setChime"
              @clear-allowed="chat.clearAllowedTools()"
            />
            <ApprovalModePicker
              :mode="approvalMode"
              :forced="forceToolApproval"
              @update:mode="chat.setApprovalMode"
            />
            <span v-if="working" class="working">
              {{ working }}<template v-if="clockStart"> · <ElapsedTime :since="clockStart" /></template>
            </span>
          </template>
        </ChatInput>
        <CommandFormModal :command="formCommand" :schema="formSchema" @submit="runCommandForm" @close="closeCommandForm" />
        <TriageQuestionModal :open="triageOpen" :submit="chat.askTriage" @close="triageOpen = false" />
        <TemplatesModal :open="templatesOpen" :draft="templatesDraft" @close="templatesOpen = false" />
        <ShareDialog :open="shareOpen" :chat-id="activeId" @close="shareOpen = false" />
        <ConfirmModal
          v-if="pendingChatAction"
          open
          :title="chatActionCopy.title"
          :message="chatActionCopy.message"
          :confirm-label="chatActionCopy.label"
          @confirm="runChatAction"
          @close="pendingChatAction = null"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.chat-view {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}
.main {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.messages {
  flex: 1;
  min-height: 0;
}
.banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 0.9em;
  color: var(--danger);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.banner button {
  padding: 2px 12px;
  border: 1px solid var(--danger);
  border-radius: var(--radius-full);
  cursor: pointer;
  color: var(--danger);
  background: transparent;
}
.loading {
  flex: 1;
  margin: 0;
  padding: 24px;
  text-align: center;
  color: var(--muted);
}
.composer-area {
  flex-shrink: 0;
}
.working {
  font-size: 0.8em;
  color: var(--muted);
}
.mobile-header, .sheet-heading {
  display: none;
}
.backdrop {
  display: none;
}

/* Wider screens: a handle on the list's edge folds it away and back. */
.collapse {
  position: absolute;
  top: 50%;
  left: 260px;
  z-index: 5;
  display: grid;
  place-items: center;
  width: 16px;
  height: 44px;
  padding: 0;
  border: 1px solid var(--border);
  border-left: none;
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  cursor: pointer;
  color: var(--muted);
  background: var(--surface);
  transform: translateY(-50%);
  transition: left 0.2s ease;
}
.collapse:hover {
  color: var(--text);
  border-color: var(--accent);
}
.collapse.collapsed {
  left: 0;
}
.collapse svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
@media (min-width: 768px) {
  .sidebar {
    transition:
      width 0.2s ease,
      padding 0.2s ease,
      visibility 0s;
  }
  /* Out of sight and out of the tab order once it has folded. */
  .sidebar.collapsed {
    width: 0;
    padding-inline: 0;
    overflow: hidden;
    border-right-width: 0;
    visibility: hidden;
    transition:
      width 0.2s ease,
      padding 0.2s ease,
      visibility 0s 0.2s;
  }
}

@media (max-width: 767px) {
  .collapse {
    display: none;
  }
  .sidebar {
    position: absolute;
    inset: auto 0 0;
    z-index: 20;
    width: 100%;
    height: min(80%, 640px);
    padding: 8px 16px 16px;
    border: 1px solid var(--border);
    border-bottom: none;
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
    background: var(--bg);
    visibility: hidden;
    transform: translateY(100%);
    transition: transform 0.2s ease, visibility 0s 0.2s;
  }
  .sidebar.open {
    visibility: visible;
    transform: none;
    transition: transform 0.2s ease;
  }
  .sheet-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: -8px;
    z-index: 2;
    padding-top: 12px;
    background: var(--bg);
  }
  .sheet-heading::before {
    content: "";
    position: absolute;
    top: 0;
    left: calc(50% - 18px);
    width: 36px;
    height: 4px;
    border-radius: var(--radius-full);
    background: var(--border);
  }
  .sheet-heading h2 { margin: 0; font-size: 1.2em; }
  .sidebar :deep(.new-chat) {
    justify-content: center;
    border-radius: var(--radius-full);
    border-color: var(--accent);
    color: var(--accent-contrast);
    background: var(--accent);
  }
  .sidebar :deep(.new-chat svg) { stroke: currentColor; }
  .sidebar :deep(.row) { min-height: 52px; }
  .sidebar :deep(.search input) { min-height: 44px; }
  .sidebar :deep(.row .title) { min-width: 0; }
  .mobile-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    min-height: 56px;
    padding: 4px 12px;
    border-bottom: 1px solid var(--border);
  }
  .mobile-brand { display: flex; align-items: center; gap: 8px; font-size: 1.2em; }
  .mobile-brand svg { width: 26px; height: 26px; }
  .mobile-header button, .sheet-heading button {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: none;
    border-radius: var(--radius-md);
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .mobile-header button:hover, .sheet-heading button:hover { color: var(--text); background: var(--surface); }
  .mobile-header button:focus-visible, .sheet-heading button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .new-mobile-chat svg, .sheet-heading svg {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .backdrop {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 10;
    background: rgba(0, 0, 0, 0.35);
  }
}
</style>
