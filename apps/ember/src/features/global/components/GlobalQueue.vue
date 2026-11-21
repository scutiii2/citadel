<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import ListRow from "../../../components/ui/lists/ListRow.vue";
import StateMessage from "../../../components/ui/status/StateMessage.vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { formatUtc } from "../../../utils/time";
import type { Share, ShareKind } from "../../sharing/api/SharingClient";
import { globalClient } from "../api/GlobalClient";
import GlobalReview from "./GlobalReview.vue";

const auth = useAuthStore();
const shares = ref<Share[]>([]);
const reviewing = ref<Share | null>(null);
const loading = ref(false);
const error = ref("");
const notice = ref("");
const kind: Record<ShareKind, string> = { file: "File", section: "Section", skill: "Skill", stack_item: "Short-term item" };
let run = 0;

async function load(): Promise<void> {
  if (!auth.hasPermission("brain.global.write")) return;
  const current = ++run;
  loading.value = true;
  error.value = "";
  try {
    const items = await globalClient.queue();
    if (current === run) shares.value = items;
  } catch (err) {
    if (current === run) error.value = errorMessage(err);
  } finally {
    if (current === run) loading.value = false;
  }
}

function clear(): void {
  run++;
  shares.value = [];
  reviewing.value = null;
  loading.value = false;
  notice.value = error.value = "";
}
watch([() => auth.account?.id, () => auth.hasPermission("brain.global.write")], clear, { flush: "sync" });
onBeforeUnmount(clear);
onMounted(load);

function finished(message: string): void {
  reviewing.value = null;
  notice.value = message;
  void load();
}
</script>

<template>
  <div class="global-queue">
    <p v-if="notice" class="feedback" role="status"><span aria-hidden="true">✓</span> {{ notice }}</p>
    <StateMessage v-if="loading" kind="loading">Loading the review queue…</StateMessage>
    <StateMessage v-else-if="error" kind="error" class="load-state" @retry="load">Could not load the queue. {{ error }}</StateMessage>
    <StateMessage v-else-if="!shares.length" kind="empty">Nothing is waiting for review.</StateMessage>
    <ul v-else class="share-list">
      <li v-for="share in shares" :key="share.id">
        <ListRow :active="reviewing?.id === share.id" @click="reviewing = share">
          <strong>{{ share.title }}</strong>
          <span class="meta">{{ kind[share.kind] }} · From {{ share.sender }} · {{ formatUtc(share.created_at) }} · {{ share.chars }} characters</span>
        </ListRow>
      </li>
    </ul>
    <GlobalReview v-if="reviewing" :share="reviewing" @close="reviewing = null" @done="finished" @decided="load" />
  </div>
</template>

<style scoped>
.share-list { list-style: none; margin: 0; padding: 0; overflow-wrap: anywhere; }
.share-list li + li { border-top: 1px solid var(--border); }
.meta { color: var(--muted); }
.feedback { margin: 0 0 12px; }
.global-queue .load-state { color: var(--text); }
.load-state :deep(button) { min-height: 44px; }
</style>
