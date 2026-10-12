<script setup lang="ts">
import { computed, onDeactivated, onMounted, reactive } from "vue";
import { useGamesStore } from "../stores/games";
import GameStage from "../components/games/GameStage.vue";
import "../components/infoPage.css";
const store = useGamesStore();
const active = computed(() => store.games.find(game => game.id === store.activeId));
const playing = computed(() => Boolean(active.value && store.launchUrl));
// Wallpapers that failed to load fall back to the initial-letter tile.
const broken = reactive(new Set<string>());
// The whole card launches the game; the Play button is its keyboard and screen-reader entry.
const play = (id: string) => { if (!store.launching) store.open(id); };
onMounted(() => store.load());
// KeepAlive detaches the iframe; its redeemed ticket cannot be reused on return.
onDeactivated(() => store.close());
</script>
<template>
  <section class="games-view info-page" :class="{ playing }"><div class="column">
    <header v-if="!playing" class="heading"><div><h2>Games</h2><p>Choose a game to play in Ember.</p></div><button class="refresh" :disabled="store.loading || store.launching" @click="store.load()">Refresh</button></header>
    <p v-if="store.error" role="alert" class="error">{{ store.error }}</p>
    <div v-if="playing && active && store.launchUrl" class="active-game">
      <!-- On wide screens the nav rail closes the game; this button is for narrow screens, where the rail is a tab bar. -->
      <button class="close-game" aria-label="Close game" @click="store.close()">✕</button>
      <GameStage :key="store.launchUrl" :game="active" :url="store.launchUrl" @close="store.close()" />
    </div>
    <p v-else-if="store.loading" role="status">Loading games…</p>
    <div v-else-if="store.games.length" class="games">
      <article v-for="game in store.games" :key="game.id" class="game-card" :data-launching="store.launching || undefined" @click="play(game.id)">
        <img v-if="game.wallpaper && !broken.has(game.id)" class="wallpaper" :src="game.wallpaper" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken.add(game.id)">
        <span v-else class="wallpaper fallback" aria-hidden="true">{{ game.name.charAt(0) }}</span>
        <span v-if="game.version" class="version">v{{ game.version }}</span>
        <div class="shade">
          <div class="text"><h3>{{ game.name }}</h3><p>{{ game.description }}</p></div>
          <span v-if="game.symbols?.length" class="symbols"><img v-for="symbol in game.symbols" :key="symbol" :src="symbol" alt="" loading="lazy" referrerpolicy="no-referrer"></span>
        </div>
        <button class="play" :disabled="store.launching" :aria-busy="store.launching" @click.stop="play(game.id)">{{ store.launching ? 'Launching…' : 'Play' }}<span class="sr-only"> {{ game.name }}</span></button>
      </article>
    </div>
    <p v-else>No games available for your account</p>
  </div></section>
</template>
<style scoped>
.games-view { flex: 1; min-height: 0; overflow-y: auto; padding: 24px 16px; }
.column { max-width: 980px; margin: 0 auto; }
.heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
h2 { margin: 0; font-size: 1.2em; } h3 { margin: 0; font-size: 1em; } p { color: var(--muted); }
.games { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 300px)); gap: 16px; }
.game-card { cursor: pointer; position: relative; aspect-ratio: 16 / 10; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); transition: transform .15s ease; }
.game-card:hover, .game-card:focus-within { transform: translateY(-2px); }
.wallpaper { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.wallpaper.fallback { display: flex; align-items: center; justify-content: center; font-size: 4em; font-weight: 600; color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--code-bg)); }
.version { position: absolute; top: 12px; left: 12px; padding: 2px 6px; border-radius: var(--radius-sm); background: rgb(0 0 0 / 50%); color: white; font-size: 0.75em; }
.shade { position: absolute; left: 0; right: 0; bottom: 0; padding: 36px 14px 12px; background: rgb(0 0 0 / 55%); color: white; }
.shade { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
.shade .text { min-width: 0; }
.shade h3 { font-size: 1.05em; }
.symbols { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px; max-width: 45%; }
.symbols img { width: 22px; height: 22px; object-fit: contain; }
.shade p { margin: 2px 0 0; color: rgb(255 255 255 / 85%); font-size: 0.9em; line-height: 1.4; max-height: 0; opacity: 0; overflow: hidden; transition: max-height .15s ease, opacity .15s ease; }
.game-card:hover .shade p, .game-card:focus-within .shade p, .game-card[data-launching] .shade p { max-height: 3em; opacity: 1; }
button { border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--bg); color: var(--text); padding: 7px 14px; cursor: pointer; }
button.play { position: absolute; top: 12px; right: 12px; background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; opacity: 0; transition: opacity .15s ease; }
button.play:focus-visible, .game-card:hover button.play, .game-card[data-launching] button.play { opacity: 1; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (hover: none) { .shade p { max-height: 3em; opacity: 1; } button.play { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .game-card, .shade p, button.play { transition: none; } .game-card:hover, .game-card:focus-within { transform: none; } }
button:disabled { opacity: .6; cursor: default; } button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
p.error { color: var(--danger); }
/* While a game runs it takes the whole page: no heading, no column, no page scroll. */
.games-view.playing { display: flex; padding: 12px; overflow: hidden; }
.playing .column { display: flex; flex-direction: column; flex: 1; min-height: 0; max-width: none; margin: 0; }
.active-game { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.active-game { position: relative; }
.close-game { display: none; }
@media (max-width: 767px) {
  .close-game { display: grid; place-items: center; position: absolute; top: 8px; right: 8px; z-index: 5; width: 32px; height: 32px; padding: 0; background: rgb(0 0 0 / 55%); border-color: rgb(255 255 255 / 25%); color: white; }
}
</style>
