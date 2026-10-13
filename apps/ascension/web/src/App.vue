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
import EmTabs from "./components/ui/EmTabs.vue";
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
const shopControls = ref<HTMLElement | null>(null);
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
const touchOnly = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(hover: none) and (pointer: coarse)").matches;
const hasAccount = computed(() => session.status === "ready" && store.loaded && !store.unavailable && store.profile !== null);
/** A battle being fought or replayed; its responsive layout keeps the Back header visible. */
const fighting = computed(() => screen.value === "game" && tab.value === "battle" && !!store.battle && !(store.battle.result && !playback.busy));
const tab = ref<Tab>("collection");
const tabs = [{ value: "battle", label: "Battle", icon: "play" as const }, { value: "collection", label: "Collection", icon: "book" as const }];

function play(target: PlayTarget): void {
  tab.value = target;
  screen.value = "game";
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
    <EmPanel v-if="touchOnly" class="state" role="alert"><EmIcon name="warning" :size="40" /><h2 class="em-pixel">Ascension is PC only</h2><p>Open this game on a computer with a mouse and keyboard.</p></EmPanel>
    <EmShell v-else :destination="screen === 'menu' ? 'Main menu' : screen === 'starter' ? 'Choose your starter' : tab === 'collection' ? 'Your collection' : tab === 'shop' ? 'Forge Shop' : store.battle?.result ? 'Battle result' : store.battle ? 'Forge Arena' : 'Quick battle'" :insignia="hasAccount ? store.profile!.insignia : null" :shop-enabled="hasAccount" :shop-open="tab === 'shop'" @shop="play('shop')">
      <template v-if="session.status === 'ready' && store.loaded && !store.unavailable && screen !== 'menu'" #navigation>
        <h1 class="screen-brand em-pixel"><button type="button" class="menu-link" aria-label="Main menu" title="Main menu" @click="screen = 'menu'">ASCENSION</button></h1>
        <EmTabs v-if="screen === 'game'" :model-value="tab" :options="tabs" ariaLabel="Ascension sections" @update:model-value="value => play(value as PlayTarget)" />
      </template>
      <template #tools>
        <div v-if="screen === 'game' && tab === 'shop'" id="shop-mode-controls" ref="shopControls" class="header-controls" />
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
            <CollectionPanel @navigate="play" />
          </div>

          <div v-else-if="tab === 'battle'" class="tab-body">
            <template v-if="store.battle">
              <BattleResult v-if="store.battle.result && !playback.busy" :battle="store.battle" />
              <template v-else>
                <div class="battle-view">
                  <div class="battle-stage">
                    <BattleArena :battle="store.battle" />
                    <div class="battle-side"><BattleControls :battle="store.battle" /><RoundLog :battle="store.battle" /></div>
                  </div>
                  <div class="battle-bottom"><ActionBar :battle="store.battle" /></div>
                </div>
                <EmblemPrompt />
              </template>
            </template>
            <EncounterPanel v-else />
          </div>

          <ShopPanel v-else class="tab-body" :controls-target="shopControls" />
        </template>
      </template>
    </EmShell>
  </section>
</template>





<style scoped>
.ascension-page { flex:1; height:100%; min-height:0; box-sizing:border-box; padding:12px 16px; overflow:hidden; }
.menu-link { display:flex; align-items:center; padding:0; border:0; color:inherit; background:transparent; font:inherit; cursor:pointer; }
.back-arrow { transform:rotate(180deg); } .screen-brand { margin:0; flex:none; font-size:28px; font-weight:700; color:var(--em-accent); letter-spacing:.25px; }
.subtle-settings { display:flex; align-items:center; justify-content:center; width:28px; height:32px; padding:0; border:0; color:var(--em-muted); background:transparent; cursor:pointer; }
.battle-stage { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:6px; align-items:stretch; } .battle-bottom { margin-top:6px; } .status { margin-bottom:8px; } .state { max-width:680px; margin:48px auto; display:flex; flex-direction:column; align-items:center; gap:16px; padding:32px; text-align:center; } .state p { color:var(--em-muted); } .skeletons { display:flex; gap:12px; } .skeleton { width:100px; height:120px; background:var(--em-raised); } .settings-content { display:flex; flex-direction:column; gap:16px; }
@media(max-width:1100px) { .screen-brand { font-size:22px; } }
@media(max-width:900px) { .battle-view{display:flex;flex-direction:column;gap:6px}.battle-stage{display:contents}.battle-stage>.arena{order:1}.battle-bottom{order:2;margin-top:0}.battle-side{order:3} }
@media(max-width:700px) { .ascension-page { padding:6px; } .screen-brand { font-size:16px; } }
.battle-side{display:flex;flex-direction:column;gap:6px;min-width:0}.screen-brand{white-space:nowrap}.screen-brand + :deep(.em-tabs){padding:0;gap:0}.screen-brand + :deep(.tab){min-height:34px;font-size:12px;padding:7px 10px}@media(max-width:1100px){.screen-brand + :deep(.tab){padding:6px;font-size:11px}}
</style>
