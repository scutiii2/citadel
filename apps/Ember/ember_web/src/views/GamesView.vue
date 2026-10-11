<script setup lang="ts">
import { computed, onDeactivated, onMounted } from "vue";
import { useGamesStore } from "../stores/games";
import GameStage from "../components/games/GameStage.vue";
import "../components/infoPage.css";
const store = useGamesStore();
const active = computed(() => store.games.find(game => game.id === store.activeId));
onMounted(() => store.load());
// KeepAlive detaches the iframe; its redeemed ticket cannot be reused on return.
onDeactivated(() => store.close());
</script>
<template>
  <section class="games-view info-page"><div class="column">
    <header class="heading"><div><h2>Games</h2><p>Choose a game to play in Ember.</p></div><button class="refresh" :disabled="store.loading || store.launching" @click="store.load()">Refresh</button></header>
    <p v-if="store.error" role="alert" class="error">{{ store.error }}</p>
    <div v-if="active && store.launchUrl" class="active-game">
      <header class="stage-head"><h3>{{ active.name }}</h3><button class="close-game" @click="store.close()">Close game</button></header>
      <GameStage :key="store.launchUrl" :game="active" :url="store.launchUrl" @close="store.close()" />
    </div>
    <p v-else-if="store.loading" role="status">Loading games…</p>
    <div v-else-if="store.games.length" class="games">
      <article v-for="game in store.games" :key="game.id" class="game-card"><h3>{{ game.name }}</h3><p>{{ game.description }}</p><button class="play" :disabled="store.launching" :aria-busy="store.launching" @click="store.open(game.id)">{{ store.launching ? 'Launching…' : 'Play' }}</button></article>
    </div>
    <p v-else>No games available for your account</p>
  </div></section>
</template>
<style scoped>
.games-view { flex: 1; min-height: 0; overflow-y: auto; padding: 24px 16px; }
.column { max-width: 980px; margin: 0 auto; }
.heading, .stage-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
h2 { margin: 0; font-size: 1.2em; } h3 { margin: 0; font-size: 1em; } p { color: var(--muted); }
.games { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.game-card { border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); padding: 16px; }
button { border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--bg); color: var(--text); padding: 7px 14px; cursor: pointer; }
button.play { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; }
button:disabled { opacity: .6; cursor: default; } button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
p.error { color: var(--danger); }
</style>
