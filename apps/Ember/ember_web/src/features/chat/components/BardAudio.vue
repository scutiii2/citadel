<script setup lang="ts">
import { computed } from "vue";
import { useAuthStore } from "../../../stores/auth";

/** In-chat player for a Bard answer. The audio streams through ember_api: the
 * page's content security policy only allows same-origin media, so it never
 * loads from Bard itself. */
const props = defineProps<{ fileId: string }>();

const auth = useAuthStore();
const url = computed(() => `/api/bard/audio/${encodeURIComponent(props.fileId)}`);
</script>

<template>
  <div class="bard-audio">
    <audio controls preload="none" :src="url" aria-label="Spoken answer"></audio>
    <a v-if="auth.hasPermission('files.download')" class="save-audio" :href="url" download="bard.mp3">Download MP3</a>
  </div>
</template>

<style scoped>
.bard-audio {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 6px 0;
}
.bard-audio audio {
  max-width: 100%;
}
.save-audio {
  color: var(--accent);
}
</style>
