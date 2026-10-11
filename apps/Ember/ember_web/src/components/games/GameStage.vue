<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from "vue";
import type { GameInfo } from "../../api/GamesClient";
import { GameMessages } from "./gameMessages";
const props = defineProps<{ game: GameInfo; url: string }>();
const emit = defineEmits<{ close: [] }>();
const frame = ref<HTMLIFrameElement | null>(null);
const ready = ref(false);
const policy = computed(() => new GameMessages(props.game.url, () => frame.value?.contentWindow ?? null));
const allowed = computed(() => policy.value.allows(props.url));
let listening = false;
function message(event: MessageEvent): void {
  if (!allowed.value) return;
  const data = policy.value.receive(event); if (!data) return;
  if (data.type === "ready") ready.value = true;
  else if (data.type === "close") emit("close");
}
function listen(): void { if (!listening) { window.addEventListener("message", message); listening = true; } }
function stop(): void { window.removeEventListener("message", message); listening = false; }
watch(() => props.url, () => { ready.value = false; });
onMounted(listen); onActivated(listen); onDeactivated(stop); onUnmounted(stop);
</script>
<template>
  <p v-if="!allowed" role="alert">Game URL is not allowed</p>
  <div v-else class="game-stage">
    <p v-if="!ready" role="status">Opening {{ game.name }}…</p>
    <iframe ref="frame" :src="url" :title="game.name" sandbox="allow-scripts allow-same-origin allow-forms" referrerpolicy="no-referrer" />
  </div>
</template>
<style scoped>
/* The stage fills its parent; the game scrolls inside its own frame, so its resize messages are ignored. */
.game-stage { display: flex; flex-direction: column; flex: 1; min-height: 0; width: 100%; }
iframe { display: block; flex: 1; min-height: 0; width: 100%; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
p { color: var(--muted); }
</style>
