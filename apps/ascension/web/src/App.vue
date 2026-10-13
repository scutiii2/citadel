<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, nextTick, ref, watch } from "vue";
import "./components/fonts";
import "./components/theme.css";
import ActionBar from "./components/ActionBar.vue";
import BattleArena from "./components/BattleArena.vue";
import { usePlaybackStore } from "./stores/playback";
import BattleControls from "./components/BattleControls.vue";
import BattleResult from "./components/BattleResult.vue";
import CollectionPanel from "./components/CollectionPanel.vue";
import EmShell from "./components/EmShell.vue";
import HowToPlayDialog from "./components/HowToPlayDialog.vue";
import EmblemPrompt from "./components/EmblemPrompt.vue";
import EncounterPanel from "./components/EncounterPanel.vue";
import RoundLog from "./components/RoundLog.vue";
import MainMenu, { type PlayTarget } from "./components/MainMenu.vue";
import ShopPanel from "./components/ShopPanel.vue";
import StarterPick from "./components/StarterPick.vue";
import EmButton from "./components/ui/EmButton.vue";
import EmDialog from "./components/ui/EmDialog.vue";
import EmConfirm from "./components/ui/EmConfirm.vue";
import EmIcon from "./components/ui/EmIcon.vue";
import EmNotice from "./components/ui/EmNotice.vue";
import EmPanel from "./components/ui/EmPanel.vue";
import EmTabs, { type EmTabOption } from "./components/ui/EmTabs.vue";
import { useSessionStore } from "./stores/session";
import { useAscensionStore } from "./stores/ascension";

/** Ascension: a main menu, then collect Ascended, battle wild ones, spend Insignia.
 * The game has its own theme (components/theme.css). Its store's loop runs
 * only while the page is attached and the browser tab is visible. */
type Tab = PlayTarget;
type Screen = "menu" | "starter" | "game";

const session = useSessionStore();
const store = useAscensionStore();
const playback = usePlaybackStore();
const page = ref<HTMLElement | null>(null);
let observer: ResizeObserver | null = null;
let stopMessages: (() => void) | null = null;
function notifyContentSize(): void {
  const mast = page.value?.querySelector<HTMLElement>(".mast");
  const main = page.value?.querySelector<HTMLElement>(".main");
  if (session.status === "ready" && mast && main) {
    session.bridge?.notifyResize(mast.getBoundingClientRect().height + main.scrollHeight);
  }
}
const screen = ref<Screen>("menu");
const showingHelp = ref(false);
const showingSettings = ref(false);
const confirmingReset = ref(false);
const hasAccount = computed(() => session.status === "ready" && store.loaded && !store.unavailable && store.profile !== null);
const inBattle = computed(() => store.profile?.active_battle != null || store.battle?.status === "active");
/** A battle being fought (or replayed): on a narrow screen only the battle shows, the masthead steps aside. */
const fighting = computed(() => screen.value === "game" && tab.value === "battle" && !!store.battle && !(store.battle.result && !playback.busy));
const tab = ref<Tab>("collection");
const tabs: EmTabOption[] = [
  { value: "battle", label: "Battle", icon: "play" },
  { value: "collection", label: "Collection", icon: "book" },
];
function play(target: PlayTarget): void {
  tab.value = target;
  screen.value = "game";
}

function selectTab(value: string): void {
  tab.value = value as Tab;
}

async function reset(): Promise<void> {
  if (inBattle.value || store.busy) return;
  if (await store.resetProgress()) {
    confirmingReset.value = false;
    showingSettings.value = false;
  }
}

// Newly found encounters enter planning; restored saves and battles start at the menu.
watch(() => store.encounter?.id ?? null, (id, previous) => {
  if (id !== null && previous !== undefined) play("battle");
});
// Losing the save (reset) sends the page back to the menu.
watch(
  () => store.needsStarter,
  (needs) => {
    if (needs) {
      screen.value = "menu";
      showingHelp.value = false;
      showingSettings.value = false;
      confirmingReset.value = false;
    }
  },
);

watch(() => session.status, async (status) => {
  if (status === "ready") {
    store.attach();
    await nextTick();
    session.bridge?.notifyReady();
    notifyContentSize();
  } else store.detach();
});
onMounted(async () => {
  stopMessages = session.bridge?.listen(() => session.end()) ?? null;
  if (typeof ResizeObserver !== "undefined" && page.value) {
    observer = new ResizeObserver(notifyContentSize);
    for (const content of page.value.querySelectorAll(".mast, .main")) observer.observe(content);
  }
  if (session.status === "ready") store.attach();
  else await session.connect();
});
onActivated(() => { if (session.status === "ready") store.attach(); });
onDeactivated(() => store.detach());
onUnmounted(() => { observer?.disconnect(); stopMessages?.(); store.detach(); });
</script>

<template>
  <section ref="page" class="em-root ascension-page" :class="{ fighting }">
    <EmShell :destination="screen === 'menu' ? 'Main menu' : screen === 'starter' ? 'Starter selection' : tab === 'battle' ? 'Quick battle' : tab === 'collection' ? 'Collection' : 'Shop'" :insignia="hasAccount ? store.profile!.insignia : null" :shop-enabled="hasAccount" :shop-open="tab === 'shop'" @shop="play('shop')">
      <template v-if="hasAccount" #actions>
        <EmButton class="account-action" aria-label="How to play" title="How to play" @click="showingHelp = true"><EmIcon name="book" /><span class="action-label">How to play</span></EmButton>
        <EmButton class="account-action" aria-label="Settings" title="Settings" @click="showingSettings = true"><EmIcon name="settings" /><span class="action-label">Settings</span></EmButton>
      </template>
      <template v-if="session.status === 'ready' && store.loaded && !store.unavailable && screen !== 'menu'" #navigation>
        <button type="button" class="menu-link" aria-label="Main menu" @click="screen = 'menu'"><EmIcon name="arrow" class="back-arrow" /></button>
        <h1 class="screen-brand em-pixel">ASCENSION</h1>
        <EmTabs v-if="screen === 'game'" :model-value="tab" :options="tabs" ariaLabel="Ascension sections" @update:model-value="selectTab" />
      </template>
      <EmPanel v-if="session.status !== 'ready'" class="state" :role="session.status === 'connecting' ? 'status' : 'alert'">
        <EmIcon name="flame" :size="40" />
        <h2 class="em-pixel">{{ session.status === 'connecting' ? 'Connecting to Ember…' : session.status === 'ended' ? 'Session ended, reopen the game from Ember' : 'Open this game from Ember' }}</h2>
        <p v-if="session.status === 'failed'">This launch could not be verified. Reopen Ascension from Ember to try again.</p>
        <p v-else-if="session.status !== 'connecting'">Choose Ascension on Ember’s Games page to start a session.</p>
      </EmPanel>
      <EmPanel v-else-if="store.unavailable" class="state unavailable" role="alert">
        <EmIcon name="warning" :size="40" />
        <h2 class="em-pixel">Ascension is not available right now</h2>
        <p>Try connecting to the forge again.</p>
        <EmButton variant="primary" :disabled="store.loading" @click="store.retry()">Retry</EmButton>
      </EmPanel>

      <EmPanel v-else-if="!store.loaded" class="state loading">
        <EmIcon name="flame" :size="40" />
        <h2 class="em-pixel">Loading your Ascended…</h2>
        <p>Preparing your collection and wallet.</p>
        <EmNotice v-if="store.error" tone="error">Could not load Ascension: {{ store.error }}</EmNotice>
        <EmButton v-if="store.error && !store.loading" @click="store.retry()">Retry</EmButton>
        <div v-else class="skeletons" aria-hidden="true"><span v-for="n in 4" :key="n" class="skeleton" /></div>
      </EmPanel>

      <template v-else>
        <EmNotice v-if="store.reconnecting" class="status">Reconnecting… Your battle will resume when connected.</EmNotice>
        <MainMenu v-if="screen === 'menu'" @new-game="screen = 'starter'" @play="play" />
        <StarterPick v-else-if="screen === 'starter'" hide-heading @back="screen = 'menu'" @started="play('collection')" />

        <template v-else>
          <EmNotice v-if="store.error" tone="error" class="status">{{ store.error }}</EmNotice>

          <div v-if="tab === 'collection'" class="tab-body">
            <CollectionPanel />
          </div>

          <div v-else-if="tab === 'battle'" class="tab-body">
            <template v-if="store.battle">
              <BattleResult v-if="store.battle.result && !playback.busy" :battle="store.battle" />
              <template v-else>
                <div class="battle-stage">
                  <BattleArena :battle="store.battle" />
                  <div class="battle-side">
                    <BattleControls :battle="store.battle" />
                    <RoundLog :battle="store.battle" />
                  </div>
                </div>
                <div class="battle-bottom"><ActionBar :battle="store.battle" /></div>
                <EmblemPrompt />
              </template>
            </template>
            <EncounterPanel v-else />
          </div>

          <ShopPanel v-else class="tab-body" />
        </template>
      </template>
    </EmShell>
    <HowToPlayDialog :open="hasAccount && showingHelp" @close="showingHelp = false" />
    <EmDialog :open="hasAccount && showingSettings" title="Settings" @close="showingSettings = false">
      <div class="settings-content">
        <h3>Account progression</h3>
        <p>Start again with a new starter Ascended.</p>
        <EmButton variant="danger" :disabled="inBattle || store.busy" @click="confirmingReset = true"><EmIcon name="reset" /> Reset progress</EmButton>
        <p v-if="inBattle">Finish or forfeit your battle to reset.</p>
      </div>
    </EmDialog>
    <EmConfirm :open="hasAccount && confirmingReset" title="Reset all Ascension progress?" message="You will start again with a new starter Ascended." confirm-label="Reset progress" cancel-label="Keep my progress" danger require-text="RESET" :busy="store.busy || inBattle" @confirm="reset" @close="confirmingReset = false">
      <EmNotice tone="error" class="reset-notice">This permanently removes your Ascended, Insignia, EMBLEMs and presets.</EmNotice>
      <EmNotice v-if="store.error" tone="error" class="reset-notice">{{ store.error }}</EmNotice>
    </EmConfirm>
  </section>
</template>

<style scoped>
.ascension-page {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.menu-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: var(--em-target);
  padding: 0 4px;
  border: 0;
  color: var(--em-accent);
  background: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.back-arrow {
  transform: scaleX(-1);
}
.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--em-space-3);
  padding: 48px 24px;
  text-align: center;
}
.state svg {
  color: var(--em-accent);
}
.state h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.4;
}
.state p {
  max-width: 360px;
  color: var(--em-muted);
}
.skeletons {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 20px;
  margin-top: var(--em-space-3);
}
.skeleton {
  width: 140px;
  aspect-ratio: 1060 / 1484;
  border: 1px solid var(--em-border);
  background: linear-gradient(var(--em-raised) 25%, #334756 25% 74%, var(--em-raised) 74%);
}
.status {
  margin: var(--em-space-3) 0;
}
.tab-body {
  min-width: 0;
}
.settings-content { display: flex; flex-direction: column; align-items: flex-start; gap: var(--em-space-4); }
.settings-content p { color: var(--em-muted); }
.reset-notice { margin-bottom: var(--em-space-4); }
@media (max-width: 700px) {
  .action-label { display: none; }
  .account-action { min-width: var(--em-target); padding-inline: 12px; }
  :deep(.navigation .tab) { min-width: var(--em-target); padding: 8px; gap: 0; font-size: 0; }
  :deep(.navigation .tab:first-child) { gap: 4px; font-size: 12px; }
  :deep(.navigation .em-tabs) { width: auto; }
  .menu-link { padding: 0; }
}
.battle-bottom {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--em-space-5);
  margin-top: var(--em-space-5);
}
@media (max-width: 700px) {
  .battle-bottom {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--em-space-3);
    margin-top: var(--em-space-3);
  }
  .fighting :deep(.main) { padding: var(--em-space-3) var(--em-space-3) var(--em-space-4); }
}
</style>

<style scoped>
.screen-brand { margin:0; flex:none; font-size:20px; color:var(--em-accent); text-shadow:0 2px 0 #84522d; }
.battle-side { display:flex; flex-direction:column; min-width:0; }
.battle-side > :last-child { flex:1; }
.battle-stage { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:20px; align-items:stretch; }
@media(max-width:1100px) { .screen-brand { font-size:15px; } }
@media(max-width:900px) { .battle-stage { grid-template-columns:minmax(0,1fr); } }
@media(max-width:700px) { .screen-brand { font-size:12px; } }
</style>
