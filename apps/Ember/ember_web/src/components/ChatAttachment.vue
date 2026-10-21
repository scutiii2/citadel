<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { AttachmentBlock } from "../utils/attachments";
import { useAuthStore } from "../stores/auth";
import BaseModal from "./BaseModal.vue";

const props = defineProps<{ attachment: AttachmentBlock }>();
const auth = useAuthStore();
// Accept both current and older saved image references. Never use a URL from
// attachment text: only a bounded file ID can form the authenticated local URL.
const imageId = computed(() => props.attachment.text.match(
  /^\[(?:Image|PDFMerger) file_id: ([A-Za-z0-9_-]{1,100}) \| \d+ pages \| image(?: \||\])/,
)?.[1]);
const imageUrl = computed(() => imageId.value ? `/api/attachments/files/${imageId.value}/content` : "");
const failed = ref(false);
const enlarged = ref(false);
watch(() => props.attachment, () => { failed.value = false; enlarged.value = false; });
</script>

<template>
  <div v-if="imageId" class="image-attachment">
    <div class="image-label">Image · {{ attachment.filename }}</div>
    <p v-if="!auth.hasPermission('files.download')" class="unavailable">Image preview requires file download permission.</p>
    <p v-else-if="failed" class="unavailable">Image expired or unavailable. Upload it again to view it.</p>
    <button v-else type="button" class="attachment-image" :aria-label="`Enlarge ${attachment.filename}`" @click="enlarged = true">
      <img :src="imageUrl" :alt="attachment.filename" loading="lazy" @error="failed = true; enlarged = false" />
    </button>
    <details class="attachment">
      <summary>Attachment details</summary>
      <pre>{{ attachment.text }}</pre>
    </details>
    <BaseModal :open="enlarged" :title="attachment.filename" wide @close="enlarged = false">
      <img v-if="enlarged" class="full-image" :src="imageUrl" :alt="attachment.filename" @error="failed = true; enlarged = false" />
    </BaseModal>
  </div>
  <details v-else class="attachment">
    <summary>📎 {{ attachment.filename }} ({{ attachment.chars.toLocaleString() }} characters{{ attachment.truncated ? ", cut short" : "" }})</summary>
    <pre>{{ attachment.text }}</pre>
  </details>
</template>

<style scoped>
.image-attachment { margin-top: 8px; min-width: 0; white-space: normal; }
.image-label { font-size: 0.9em; overflow-wrap: anywhere; margin-bottom: 6px; }
button.attachment-image {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg);
  cursor: zoom-in;
}
.attachment-image img { display: block; max-width: 100%; max-height: 280px; object-fit: contain; }
.full-image { display: block; max-width: 100%; height: auto; margin: 0 auto; }
.unavailable { color: var(--muted); font-size: 0.9em; }
.attachment { margin-top: 6px; font-size: 0.85em; white-space: normal; }
.attachment summary { cursor: pointer; color: var(--muted); overflow-wrap: anywhere; }
.attachment pre { margin: 6px 0 0; padding: 8px; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--code-bg); border-radius: var(--radius-md); max-height: 240px; overflow-y: auto; }
button.attachment-image:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
