<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { bardClient } from "../../../api/files/BardClient";
import PopupMenu from "../../../components/ui/menus/PopupMenu.vue";
import { useAuthStore } from "../../../stores/auth";
import { speechBatches } from "../../../utils/content/speechBatches";
import { useReadAloud } from "../composables/useReadAloud";

const props = defineProps<{ text: string; scope?: string | number | null }>();
const auth = useAuthStore();
const allowed = computed(() => auth.hasPermission("tools.execute") && auth.hasPermission("files.download"));
const audio = ref<HTMLAudioElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);
const { state, error, start, stop } = useReadAloud(audio);
const loading = ref(false);
const menu = ref<{ x: number; y: number; voices: string[] } | null>(null);
const menuError = ref("");
let request: AbortController | undefined;
const active = computed(() => state.value === "playing" || state.value === "busy");
const label = computed(() => active.value || loading.value ? "Stop reading aloud" : "Read aloud");

function reset(): void {
  request?.abort();
  request = undefined;
  menu.value = null;
  loading.value = false;
  menuError.value = "";
  stop();
}

function closeMenu(): void {
  menu.value = null;
  void nextTick(() => button.value?.focus());
}

async function toggle(): Promise<void> {
  if (active.value || loading.value) { reset(); return; }
  if (menu.value) { closeMenu(); return; }
  menuError.value = "";
  error.value = "";
  if (!speechBatches(props.text).length) { menuError.value = "There is no speakable text."; return; }
  const run = request = new AbortController();
  loading.value = true;
  try {
    const result = await bardClient.voices(run.signal);
    if (run.signal.aborted) return;
    if (!result.voices.length) { menuError.value = "No voices are installed in Bard."; return; }
    const box = button.value!.getBoundingClientRect();
    menu.value = { x: box.left, y: box.bottom, voices: result.voices };
  } catch (cause) {
    if (!run.signal.aborted) menuError.value = cause instanceof Error ? cause.message : "Could not load Bard voices.";
  } finally {
    if (request === run) { loading.value = false; request = undefined; }
  }
}

function choose(voice: string): void {
  if (!menu.value?.voices.includes(voice) || !allowed.value) return;
  closeMenu();
  void start(speechBatches(props.text), voice);
}

watch(() => [props.scope, props.text, auth.account?.id, allowed.value], reset);
onBeforeUnmount(reset);
onDeactivated(reset);
</script>

<template>
  <span v-if="allowed" class="read-aloud">
    <button ref="button" type="button" class="read-aloud-button" :aria-label="label" :title="label"
      :aria-busy="loading || state === 'busy'" :aria-expanded="menu !== null" aria-haspopup="menu" @click="toggle">
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path v-if="active || loading" d="M6 6h12v12H6z" />
        <path v-else d="m11 5-6 4H2v6h3l6 4zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14" />
      </svg>
      <span v-if="loading || state === 'busy'" class="busy-ring" aria-hidden="true" />
    </button>
    <span v-if="menuError || error" class="speech-error" role="alert">{{ menuError || error }}</span>
    <audio ref="audio" hidden preload="none" />
    <PopupMenu v-if="menu" :items="menu.voices.map((voice) => ({ id: voice, label: voice }))"
      :x="menu.x" :y="menu.y" label="Choose a voice" @select="choose" @close="closeMenu" />
  </span>
</template>

<style scoped>
.read-aloud { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
button.read-aloud-button { position: relative; display: grid; place-items: center; width: 24px; height: 24px; padding: 0; border: none; border-radius: var(--radius-sm); color: var(--muted); background: transparent; cursor: pointer; }
button.read-aloud-button:hover { color: var(--text); background: var(--code-bg); }
button.read-aloud-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.speech-error { max-width: 260px; color: var(--danger); font-size: 0.85em; overflow-wrap: anywhere; }
.busy-ring { position: absolute; inset: 0; border: 2px solid transparent; border-top-color: var(--accent); border-radius: var(--radius-full); animation: speech-spin 0.8s linear infinite; pointer-events: none; }
@keyframes speech-spin { to { transform: rotate(360deg); } }
@media (pointer: coarse), (max-width: 767px) { button.read-aloud-button { width: 44px; height: 44px; } }
</style>
