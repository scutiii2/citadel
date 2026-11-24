<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AuthCard from "../../../components/auth/AuthCard.vue";
import { safeRedirect } from "../../../router/redirect";
import { useAuthStore } from "../../../stores/auth";
import { connectServer, isDesktop, serverBase, serverError, setSessionToken } from "../../../utils/server";

// Windows app only: the first screen until a server address has answered. Nothing else opens before that.
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const EXAMPLE = "http://192.168.1.5:29601";
const previous = serverBase();
const server = ref(previous);
const error = ref(serverError());
const busy = ref(false);

onMounted(() => {
  if (!isDesktop()) void router.replace("/");
});

/** Tab or Right arrow at the end of the text finishes the example address, like a shell's ghost text. */
function complete(event: KeyboardEvent): void {
  const input = event.target as HTMLInputElement;
  const atEnd = input.selectionStart === input.value.length && input.selectionEnd === input.value.length;
  if (!atEnd || input.value === EXAMPLE || !EXAMPLE.startsWith(input.value)) return;
  event.preventDefault();
  server.value = EXAMPLE;
}

async function submit(): Promise<void> {
  if (busy.value) return;
  error.value = "";
  busy.value = true;
  try {
    const result = await connectServer(server.value);
    if (!result.ok) {
      error.value = result.error;
      return;
    }
    // A different server has other accounts: drop the old session before anything asks who is logged in.
    if (result.origin !== previous) {
      setSessionToken("");
      auth.reset();
    }
    await router.replace(safeRedirect(route.query.redirect));
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthCard title="Connect to your server" subtitle="Ember needs your Citadel server before you can log in.">
    <form @submit.prevent="submit">
      <label>
        Server address
        <input
          v-model="server"
          type="url"
          inputmode="url"
          autocomplete="off"
          spellcheck="false"
          :placeholder="EXAMPLE"
          @keydown.tab="complete"
          @keydown.right="complete"
          :aria-invalid="error ? 'true' : 'false'"
          aria-describedby="connect-help connect-error"
          required
          autofocus
        />
      </label>
      <p id="connect-help" class="help">The address of Portcullis, usually http://&lt;server-ip&gt;:29601.</p>
      <p v-if="error" id="connect-error" class="error" role="alert">{{ error }}</p>
      <button class="primary" :disabled="busy" :aria-busy="busy">{{ busy ? "Connecting ..." : "Connect" }}</button>
    </form>
  </AuthCard>
</template>

<style scoped>
.help {
  margin: -4px 0 0;
  font-size: 0.85em;
  color: var(--muted);
}
</style>
