<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AdminNav from "./components/AdminNav.vue";
import PortcullisHeader from "./components/PortcullisHeader.vue";
import ThemeSelect from "./components/ThemeSelect.vue";
import PwaStatus from "./components/layout/PwaStatus.vue";
import { pageTitle } from "./router/pages";
import { useAuthStore } from "./stores/auth";

const auth = useAuthStore();
const { account } = storeToRefs(auth);
const route = useRoute();
const router = useRouter();
const signedInShell = computed(() => account.value && !route.meta.guestOnly && route.name !== "no-access");
const title = computed(() => pageTitle(route.path));
const viewport = window.matchMedia("(max-width: 767px)");
const narrow = ref(viewport.matches);
const desktopExpanded = ref(true);
const mobileExpanded = ref(false);
const expanded = computed(() => (narrow.value ? mobileExpanded.value : desktopExpanded.value));

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
// The session can end mid-page (expired, or logged out elsewhere): any 401
// clears the account, and this sends the user back to the login page.
watch(account, (now) => {
  if (!now && !route.meta.guestOnly) void router.replace({ name: "login" });
});
</script>

<template>
  <PwaStatus app-name="Ember Admin" offline-message="Reconnect to load workspace data and make administration changes." />
  <div class="shell" :class="{ 'portcullis-shell': signedInShell }">
    <PortcullisHeader v-if="signedInShell" :key="account?.id" :title="title" :expanded="expanded" @toggle="toggleNav" />
    <ThemeSelect v-else class="guest-theme" />
    <div class="shell-body">
      <AdminNav v-if="signedInShell" v-show="!narrow || expanded" :expanded="expanded" />
      <main class="shell-page"><RouterView :key="account?.id ?? 'guest'" /></main>
    </div>
  </div>
</template>

<style scoped>
.shell { position: relative; }
.shell, .shell-page { display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; }
.shell-body { display: flex; flex: 1; min-height: 0; min-width: 0; }
.portcullis-shell .shell-page { background: var(--surface); }
.portcullis-shell :deep(.page-head-copy) { display: none; }
.portcullis-shell :deep(.page-head:not(:has(.page-actions))) { display: none; }
.guest-theme { position: absolute; inset: 8px 12px auto auto; z-index: 2; }
@media (max-width: 767px) { .shell-body { flex-direction: column; } }
</style>
