<script setup lang="ts">
import { onMounted, onBeforeUnmount } from "vue";
import { GamesAdminClient } from "../api/GamesAdminClient";
import { GameAdministration } from "../services/GameAdministration";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import "../components/infoPage.css";
const controller = new GameAdministration(new GamesAdminClient());
const state = controller.state;
onMounted(() => controller.load()); onBeforeUnmount(() => controller.dispose());
</script>
<template>
  <section class="info-page games-admin"><div class="column">
    <header><h2>Games</h2><p>Register trusted games by their base URL. Ember fetches their manifest.</p></header>
    <p v-if="state.error" class="error" role="alert">{{ state.error }}</p><p v-if="state.notice" class="notice" role="status">{{ state.notice }}</p>
    <form @submit.prevent="controller.register()"><label>Game URL<input v-model="state.url" type="url" required placeholder="http://127.0.0.1:8060" :disabled="state.busy" /></label><button type="submit" class="register" :disabled="state.busy || !state.url.trim()" :aria-busy="state.busy">{{ state.busy ? 'Saving…' : 'Register game' }}</button></form>
    <p v-if="state.loading" role="status">Loading registry…</p>
    <div v-else-if="state.games.length" class="table-wrap"><table><thead><tr><th>Name</th><th>Id</th><th>Version</th><th>URL</th><th>Status</th><th>Actions</th></tr></thead><tbody><tr v-for="game in state.games" :key="game.id"><td>{{ game.name }}</td><td><code>{{ game.id }}</code></td><td>{{ game.version }}</td><td class="url">{{ game.url }}</td><td>{{ game.enabled ? 'Enabled' : 'Disabled' }}</td><td class="actions"><button class="refresh-game" :disabled="state.busy" @click="controller.refresh(game)">Refresh</button><button class="deregister-game" :disabled="state.busy" @click="controller.askDeregister(game)">Deregister</button></td></tr></tbody></table></div>
    <p v-else>No games registered yet.</p>
    <ConfirmModal :open="state.removing !== null" title="Deregister game" :message="`Remove ${state.removing?.name ?? 'this game'} from Ember? Permission grants are kept for a later registration.`" confirm-label="Deregister" danger :require-text="state.removing?.id ?? ''" :busy="state.busy" @confirm="controller.deregister()" @close="controller.cancelDeregister()" />
  </div></section>
</template>
<style scoped>
.games-admin { flex: 1; min-height: 0; overflow-y: auto; padding: 24px 16px; }
.column { max-width: 980px; margin: 0 auto; } h2 { font-size: 1.2em; margin: 0; } p { color: var(--muted); }
form { display: flex; align-items: end; gap: 12px; margin: 20px 0; } label { flex: 1; display: flex; flex-direction: column; gap: 6px; }
input { min-width: 0; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); padding: 7px 10px; }
button { border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--bg); color: var(--text); padding: 7px 12px; cursor: pointer; }
button.register { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; }
button.deregister-game { color: var(--danger); border-color: var(--danger); } button:disabled { opacity: .6; cursor: default; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius-lg); }
table { width: 100%; border-collapse: collapse; } th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border); }
.url { overflow-wrap: anywhere; } .actions { white-space: nowrap; } .actions button + button { margin-left: 6px; }
p.error { color: var(--danger); } p.notice { color: var(--success); }
@media(max-width: 600px) { form { flex-direction: column; align-items: stretch; } }
</style>
