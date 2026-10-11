<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from "vue";
import type { GameInfo } from "../../api/GamesClient";
import { GameMessages } from "./gameMessages";
const props = defineProps<{ game: GameInfo; url: string }>();
const emit = defineEmits<{ close: [] }>();
const frame = ref<HTMLIFrameElement | null>(null);
const ready = ref(false);
const height = ref(640);
const policy = computed(() => new GameMessages(props.game.url, () => frame.value?.contentWindow ?? null));
const allowed = computed(() => policy.value.allows(props.url));
let listening = false;
function message(event: MessageEvent): void {
  if (!allowed.value) return;
  const data = policy.value.receive(event); if (!data) return;
  if (data.type === "ready") ready.value = true;
  else if (data.type === "resize") height.value = data.height;
  else emit("close");
}
function listen(): void { if (!listening) { window.addEventListener("message", message); listening = true; } }
function stop(): void { window.removeEventListener("message", message); listening = false; }
watch(() => props.url, () => { ready.value = false; height.value = 640; });
onMounted(listen); onActivated(listen); onDeactivated(stop); onUnmounted(stop);
</script>
<template>
  <p v-if="!allowed" role="alert">Game URL is not allowed</p>
  <div v-else class="game-stage">
    <p v-if="!ready" role="status">Opening {{ game.name }}…</p>
    <iframe ref="frame" :src="url" :title="game.name" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer" :style="{ height: `${height}px` }" />
  </div>
</template>
<style scoped>
.game-stage { width: 100%; }
iframe { display: block; width: 100%; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
p { color: var(--muted); }
</style>
