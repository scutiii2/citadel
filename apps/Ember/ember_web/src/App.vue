<script setup lang="ts">
import { storeToRefs } from "pinia";
import { onBeforeUnmount, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import NavRail from "./components/layout/NavRail.vue";
import AlertToasts from "./features/calendar/components/AlertToasts.vue";
import PwaStatus from "./components/layout/PwaStatus.vue";
import { usePageVisibilityStore } from "./stores/navigation/pageVisibility";
import { useAuthStore } from "./stores/auth";

const auth = useAuthStore();
usePageVisibilityStore();
const { account } = storeToRefs(auth);
const route = useRoute();
const router = useRouter();

// Mobile Safari can leave 100dvh unchanged when its keyboard opens. Keep the
// entire shell in the visible area, including when focus pans that area.
const viewport = window.visualViewport;
const rootStyle = document.documentElement.style;
function updateViewport(): void {
  // Pinch zoom must keep the normal layout so users can pan around it.
  if (!viewport || viewport.scale !== 1) {
    rootStyle.removeProperty("--app-viewport-height");
    rootStyle.removeProperty("--app-viewport-top");
    return;
  }
  rootStyle.setProperty("--app-viewport-height", `${viewport.height}px`);
  rootStyle.setProperty("--app-viewport-top", `${viewport.offsetTop}px`);
}
onMounted(() => {
  updateViewport();
  viewport?.addEventListener("resize", updateViewport);
  viewport?.addEventListener("scroll", updateViewport);
});
onBeforeUnmount(() => {
  viewport?.removeEventListener("resize", updateViewport);
  viewport?.removeEventListener("scroll", updateViewport);
  rootStyle.removeProperty("--app-viewport-height");
  rootStyle.removeProperty("--app-viewport-top");
});

// The session can end mid-page (expired, or logged out elsewhere): any 401
// clears the account, and this sends the user back to the login page.
watch(account, (now) => {
  if (!now && !route.meta.guestOnly && !route.meta.public) void router.replace({ name: "login" });
});
</script>

<template>
  <PwaStatus app-name="Ember" offline-message="Reconnect to send messages and use server tools." />
  <AlertToasts />
  <div class="shell">
    <NavRail />
    <main class="page" :class="{ 'has-tabs': account && !auth.needsVerification }">
      <!-- KeepAlive: switching to Tools and back keeps the chat (and a turn in
           flight) intact.
           Keyed by account so a
           different user never gets the previous user's cached pages. -->
      <RouterView v-slot="{ Component }">
        <KeepAlive :key="account?.id ?? 'guest'" include="ChatView,CapabilitiesView">
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex: 1;
  min-height: 0;
}
/* Fills what the rail leaves; each view manages its own scrolling. */
.page {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

@media (max-width: 767px) {
  .shell {
    flex-direction: column-reverse;
  }
}
</style>
