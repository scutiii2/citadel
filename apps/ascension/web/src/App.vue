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
import EmblemPrompt from "./components/EmblemPrompt.vue";
import EncounterPanel from "./components/EncounterPanel.vue";
import RoundLog from "./components/RoundLog.vue";
import MainMenu, { type PlayTarget } from "./components/MainMenu.vue";
import ShopPanel from "./components/ShopPanel.vue";
import StarterPick from "./components/StarterPick.vue";
import EmButton from "./components/ui/EmButton.vue";
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
/** Ascension is a PC game: a touch-first device (no hover, coarse pointer) gets a notice instead. */
const touchOnly = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(hover: none) and (pointer: coarse)").matches;
const screen = ref<Screen>("menu");
const hasAccount = computed(() => session.status === "ready" && store.loaded && !store.unavailable && store.profile !== null);
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
    <EmPanel v-if="touchOnly" class="state" role="alert">
      <EmIcon name="warning" :size="40" />
      <h2 class="em-pixel">Ascension is PC only</h2>
      <p>Open this game on a computer with a mouse and keyboard.</p>
    </EmPanel>
    <EmShell v-else :destination="screen === 'menu' ? 'Main menu' : screen === 'starter' ? 'Starter selection' : tab === 'battle' ? 'Quick battle' : tab === 'collection' ? 'Collection' : 'Shop'" :insignia="hasAccount ? store.profile!.insignia : null" :shop-enabled="hasAccount" :shop-open="tab === 'shop'" @shop="play('shop')">
      <template v-if="session.status === 'ready' && store.loaded && !store.unavailable && screen !== 'menu'" #navigation>
        <h1 class="screen-brand em-pixel"><button type="button" class="menu-link" aria-label="Main menu" title="Main menu" @click="screen = 'menu'">ASCENSION</button></h1>
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
@media (max-width: 700px) {
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
.menu-link { font:inherit; color:inherit; text-shadow:inherit; letter-spacing:inherit; } .menu-link:hover { filter:brightness(1.2); } .menu-link:focus-visible { outline:2px solid var(--em-accent); outline-offset:4px; }
.screen-brand { margin:0; flex:none; font-size:20px; color:var(--em-accent); text-shadow:0 2px 0 #84522d; }
.battle-side { display:flex; flex-direction:column; min-width:0; }
.battle-side > :last-child { flex:1; }
.battle-stage { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:20px; align-items:stretch; }
@media(max-width:1100px) { .screen-brand { font-size:15px; } }
@media(max-width:900px) { .battle-stage { grid-template-columns:minmax(0,1fr); } }
@media(max-width:700px) { .screen-brand { font-size:12px; } }
</style>
