<script setup lang="ts">
import { ref, watch } from "vue";
import BaseModal from "./BaseModal.vue";

/** A small square preview of an attached picture: click to enlarge, × to remove. The parent supplies a URL
 * the browser can load (`""` while it has none) and handles `remove`. `busy` dims it while it is read. */
const props = defineProps<{ src: string; name: string; busy?: boolean }>();
const emit = defineEmits<{ remove: [] }>();

const failed = ref(false);
const enlarged = ref(false);
watch(() => props.src, () => { failed.value = false; enlarged.value = false; });
</script>

<template>
  <div class="image-tile" :aria-busy="busy || undefined">
    <button v-if="src && !failed" type="button" class="picture" :aria-label="`Enlarge ${name}`" :title="name" @click="enlarged = true">
      <img :src="src" :alt="name" @error="failed = true; enlarged = false" />
    </button>
    <span v-else class="fallback" :title="name">{{ name }}</span>
    <button type="button" class="remove" :aria-label="`Remove ${name}`" @click="emit('remove')">
      <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
        <path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
      </svg>
    </button>
    <BaseModal :open="enlarged" :title="name" wide @close="enlarged = false">
      <img v-if="enlarged" class="full" :src="src" :alt="name" />
    </BaseModal>
  </div>
</template>

<style scoped>
.image-tile {
  position: relative;
  width: 84px;
  height: 84px;
}
.picture,
.fallback {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
}
.picture {
  cursor: zoom-in;
}
.picture img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.image-tile[aria-busy="true"] .picture {
  opacity: 0.5;
}
.fallback {
  padding: 6px;
  font-size: 0.7em;
  text-align: center;
  overflow-wrap: anywhere;
  color: var(--muted);
}
.image-tile .remove {
  position: absolute;
  top: -8px;
  right: -8px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  cursor: pointer;
  color: var(--text);
  background: var(--surface);
}
.picture:focus-visible,
.remove:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.full {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
}
@media (pointer: coarse) {
  /* A 44px target around the same small circle. */
  .image-tile .remove::after {
    content: "";
    position: absolute;
    inset: -10px;
  }
}
</style>
