<script setup lang="ts">
import PasswordInput from "../../../components/ui/forms/PasswordInput.vue";
import { ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import AuthCard from "../../../components/auth/AuthCard.vue";
import { errorMessage } from "../../../utils/errors";
import { safeRedirect } from "../../../router/redirect";
import { useAuthStore } from "../../../stores/auth";
import { isDesktop, serverBase, setServerBase } from "../../../utils/server";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const desktop = isDesktop();
const server = ref(serverBase());
const username = ref("");
const password = ref("");
const error = ref("");
const busy = ref(false);

async function submit(): Promise<void> {
  if (busy.value) return;
  error.value = "";
  if (desktop && !setServerBase(server.value)) {
    error.value = "Enter the server address, like https://ember.example or http://192.168.1.5:29601.";
    return;
  }
  busy.value = true;
  try {
    await auth.login(username.value.trim(), password.value);
    password.value = "";
    await router.replace(safeRedirect(route.query.redirect));
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthCard title="Log in" subtitle="Welcome back to Ember.">
    <form @submit.prevent="submit">
      <label v-if="desktop">
        Server
        <input v-model="server" inputmode="url" autocomplete="url" placeholder="http://127.0.0.1:29601" required />
      </label>
      <label>
        Username
        <input v-model="username" autocomplete="username" required autofocus />
      </label>
      <PasswordInput label="Password" v-model="password" autocomplete="current-password" required />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" :disabled="busy" :aria-busy="busy">{{ busy ? "Logging in ..." : "Log in" }}</button>
    </form>
    <template #footer>
      Have an invite code? <RouterLink to="/register">Create an account</RouterLink>
    </template>
  </AuthCard>
</template>
