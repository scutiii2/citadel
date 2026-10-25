<script setup lang="ts">
import { computed, ref } from "vue";
import { useAuthStore } from "../../../stores/auth";

/** In-chat player for a Bard answer. The audio streams through ember_api: the
 * page's content security policy only allows same-origin media, so it never
 * loads from Bard itself. A hidden <audio> plays it; the controls are ours so
 * the card matches the rest of the chat. */
const props = defineProps<{ fileId: string; voice?: string; durationS?: number | null }>();

const auth = useAuthStore();
const url = computed(() => `/api/bard/audio/${encodeURIComponent(props.fileId)}`);

const audio = ref<HTMLAudioElement | null>(null);
const playing = ref(false);
const failed = ref(false);
const current = ref(0);
const total = ref(props.durationS ?? 0);

const meta = computed(() => [props.durationS != null ? `${props.durationS.toFixed(1)} s` : "", props.voice].filter(Boolean).join(" · "));

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function toggle(): void {
  const el = audio.value;
  if (!el) return;
  if (el.paused) el.play().catch(() => { failed.value = true; });
  else el.pause();
}

function seek(event: Event): void {
  if (audio.value) audio.value.currentTime = Number((event.target as HTMLInputElement).value);
}

function onDuration(): void {
  const length = audio.value?.duration;
  if (length && Number.isFinite(length)) total.value = length;
}
</script>

<template>
  <div class="bard-audio" role="group" aria-label="Spoken answer">
    <div class="head">
      <span class="tag">SPOKEN ANSWER</span>
      <span v-if="meta" class="meta">{{ meta }}</span>
    </div>
    <p v-if="failed" class="failed">Audio unavailable. Try again, or ask for it once more.</p>
    <div v-else class="controls">
      <button type="button" class="play" :aria-label="playing ? 'Pause' : 'Play'" @click="toggle">
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path v-if="playing" d="M4 3h3v10H4zM9 3h3v10H9z" />
          <path v-else d="M5 3l8 5-8 5z" />
        </svg>
      </button>
      <input
        class="seek"
        type="range"
        min="0"
        :max="total || 1"
        step="0.01"
        :value="current"
        aria-label="Seek"
        @input="seek"
      />
      <span class="clock">{{ clock(current) }} / {{ clock(total) }}</span>
    </div>
    <a v-if="auth.hasPermission('files.download')" class="save-audio" :href="url" download="bard.mp3">
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2v8M5 7l3 3 3-3M3 13h10" /></svg>
      Download MP3
    </a>
    <audio
      ref="audio"
      preload="none"
      :src="url"
      @play="playing = true"
      @pause="playing = false"
      @ended="playing = false"
      @timeupdate="current = audio?.currentTime ?? 0"
      @loadedmetadata="onDuration"
      @durationchange="onDuration"
      @error="failed = true; playing = false"
    ></audio>
  </div>
</template>

<style scoped>
.bard-audio {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 420px;
  margin: 8px 0;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.tag {
  font-size: 0.7em;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.meta {
  font-size: 0.85em;
  color: var(--muted);
  text-align: right;
  overflow-wrap: anywhere;
}
.controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.play {
  flex: none;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-full);
  background: var(--accent);
  color: var(--accent-contrast);
  cursor: pointer;
  transition: background 0.15s ease;
}
.play:hover {
  background: color-mix(in srgb, var(--accent) 85%, var(--text));
}
.play svg {
  width: 16px;
  height: 16px;
  fill: currentColor;
}
.seek {
  flex: 1;
  min-width: 0;
  height: 20px;
  margin: 0;
  accent-color: var(--accent);
  cursor: pointer;
}
.clock {
  flex: none;
  font-family: var(--mono);
  font-size: 0.85em;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.failed {
  margin: 0;
  font-size: 0.9em;
  color: var(--muted);
}
.save-audio {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--text);
  font-size: 0.85em;
  text-decoration: none;
  transition: border-color 0.15s ease;
}
.save-audio svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: var(--accent);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.save-audio:hover {
  border-color: var(--accent);
}
.play:focus-visible,
.seek:focus-visible,
.save-audio:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
@media (max-width: 767px) {
  .play {
    width: 44px;
    height: 44px;
  }
  .seek {
    height: 44px;
  }
  .save-audio {
    align-self: stretch;
    justify-content: center;
    min-height: 44px;
  }
}
</style>
