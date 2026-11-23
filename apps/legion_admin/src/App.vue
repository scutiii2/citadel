<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import LegionHeader from "./components/LegionHeader.vue";
import LegionNav from "./components/LegionNav.vue";
import { useAuthStore } from "./stores/auth";
import { LEGION_PAGES } from "./router/pages";

const { account } = storeToRefs(useAuthStore());
const route = useRoute();
const router = useRouter();
const signedInShell = computed(() => account.value && !route.meta.guestOnly && route.name !== "no-access");
const title = computed(() => LEGION_PAGES.find((page) => page.to === route.path)?.label ?? "");
const viewport = window.matchMedia("(max-width: 767px)");
const narrow = ref(viewport.matches);
const desktopExpanded = ref(true);
const mobileExpanded = ref(false);
const expanded = computed(() => narrow.value ? mobileExpanded.value : desktopExpanded.value);

function syncViewport(event: MediaQueryListEvent) {
  narrow.value = event.matches;
  mobileExpanded.value = false;
}

function toggleNav() {
  if (narrow.value) mobileExpanded.value = !mobileExpanded.value;
  else desktopExpanded.value = !desktopExpanded.value;
}

onMounted(() => viewport.addEventListener("change", syncViewport));
onUnmounted(() => viewport.removeEventListener("change", syncViewport));
watch(() => route.fullPath, () => { mobileExpanded.value = false; });
watch(account, (now) => {
  if (!now && !route.meta.guestOnly) void router.replace({ name: "login" });
});
</script>

<template>
  <div class="shell" :class="{ 'legion-shell': signedInShell }">
    <LegionHeader v-if="signedInShell" :key="account?.id" :title="title" :expanded="expanded" @toggle="toggleNav" />
    <div class="shell-body">
      <LegionNav v-if="signedInShell" v-show="!narrow || expanded" :expanded="expanded" />
      <main class="shell-page"><RouterView :key="account?.id ?? 'guest'" /></main>
    </div>
  </div>
</template>

<style scoped>
.shell, .shell-page { display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; }
.shell-body { display: flex; flex: 1; min-height: 0; min-width: 0; }
.legion-shell .shell-page { background: var(--surface); }
.legion-shell :deep(.page-head-copy) { display: none; }
.legion-shell :deep(.page-head:not(:has(.page-actions))) { display: none; }
@media (max-width: 767px) { .shell-body { flex-direction: column; } }
</style>
