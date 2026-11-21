<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { useAuthStore } from "../../stores/auth";
import { saveFile } from "../../utils/server";
import type { DownloadCard } from "../../utils/content/downloads";
import { formatFileSize } from "../../utils/content/downloads";

const auth = useAuthStore();

const props = defineProps<{ downloads: DownloadCard[] }>();

const failed = ref("");

// Time left is read from the clock, so a card that sits in a chat for an hour still counts down.
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | null = null;
function stopTimer(): void {
  if (timer) clearInterval(timer);
  timer = null;
}
watch(
  () => props.downloads.some((card) => card.expiresAt !== undefined),
  (needed) => {
    stopTimer();
    if (needed) {
      now.value = Date.now();
      timer = setInterval(() => (now.value = Date.now()), 30_000);
    }
  },
  { immediate: true },
);
onBeforeUnmount(stopTimer);

function expired(card: DownloadCard): boolean {
  return card.expiresAt !== undefined && card.expiresAt * 1000 <= now.value;
}

function timeLeft(card: DownloadCard): string {
  if (card.expiresAt === undefined) return "";
  if (expired(card)) return "Expired";
  return `Expires in ${Math.ceil((card.expiresAt * 1000 - now.value) / 60_000)} min`;
}

async function save(event: Event, card: DownloadCard): Promise<void> {
  failed.value = await saveFile(event, card.href ?? "", card.filename);
}

function size(card: DownloadCard): string {
  const text = formatFileSize(card.bytes);
  return text ? ` (${text})` : "";
}
</script>

<template>
  <div v-if="downloads.length" class="downloads">
    <div v-for="(card, i) in downloads" :key="i" class="card">
      <div class="tag">{{ card.label }}</div>
      <span v-if="expired(card)" class="file expired" aria-disabled="true">{{ card.filename }}{{ size(card) }}</span>
      <a v-else-if="card.href && auth.hasPermission('files.download')" class="file" :href="card.href" download @click="save($event, card)">⬇ Download {{ card.filename }}{{ size(card) }}</a>
      <span v-else class="file unavailable" title="This file cannot be downloaded from here">
        {{ card.filename }}{{ size(card) }} (unavailable)
      </span>
      <div v-if="card.expiresAt !== undefined" class="left">{{ timeLeft(card) }}</div>
    </div>
    <p v-if="failed" class="failed" role="alert">{{ failed }}</p>
  </div>
</template>

<style scoped>
.downloads {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.tag {
  font-size: 0.7em;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 3px;
}
.file {
  display: inline-block;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--code-bg);
  color: var(--text);
  font-size: 0.9em;
  text-decoration: none;
}
.failed {
  margin: 0;
  font-size: 0.85em;
  color: var(--danger, var(--muted));
}
a.file:hover {
  border-color: var(--accent);
}
.unavailable,
.expired {
  color: var(--muted);
}
.expired {
  text-decoration: line-through;
}
.left {
  margin-top: 3px;
  font-size: 0.75em;
  color: var(--muted);
}
</style>
