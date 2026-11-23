<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import AuthCard from "../../../components/auth/AuthCard.vue";
import { errorMessage } from "../../../utils/errors";
import { useLogout } from "../../../composables/useLogout";
import { useAuthStore } from "../../../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const code = ref("");
const error = ref("");
const codeSent = ref(false);
const busy = ref(false);
const action = ref<"verify" | "resend" | null>(null);
const codeError = ref(false);

const email = computed(() => auth.account?.email ?? "your address");

async function submit(): Promise<void> {
  if (busy.value) return;
  error.value = ""; codeError.value = false;
  busy.value = true; action.value = "verify";
  try {
    await auth.verifyEmail(code.value.trim());
    await router.replace({ name: "chat" });
  } catch (err) {
    codeError.value = true;
    error.value = errorMessage(err);
  } finally {
    busy.value = false; action.value = null;
  }
}

async function resend(): Promise<void> {
  if (busy.value) return;
  error.value = "";
  codeError.value = false;
  busy.value = true; action.value = "resend";
  try {
    await auth.resendVerification();
    codeSent.value = true;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false; action.value = null;
  }
}

const logout = useLogout();
</script>

<template>
  <AuthCard title="Verify your email" :subtitle="`Confirm ${email} to use Ember.`">
    <form @submit.prevent="submit">
      <button type="button" class="primary" :disabled="busy" :aria-busy="action === 'resend'" @click="resend">
        {{ action === 'resend' ? "Sending…" : codeSent ? "Send a new code" : "Email me a code" }}
      </button>
      <p v-if="codeSent && !error && action !== 'resend'" class="notice" role="status">A code was sent to {{ email }}. It expires in 15 minutes.</p>
      <label>
        Verification code
        <input v-model="code" :aria-invalid="codeError" :aria-describedby="codeError ? 'verification-error' : undefined" autocomplete="one-time-code" spellcheck="false" required autofocus />
      </label>
      <p v-if="error" class="error" role="alert" id="verification-error">{{ error }}</p>
      <button type="submit" class="primary" :disabled="busy" :aria-busy="action === 'verify'">{{ action === 'verify' ? "Verifying…" : "Verify" }}</button>
    </form>
    <template #footer>
      <RouterLink to="/account">Change email</RouterLink>
      &middot;
      <button type="button" class="link-button" @click="logout">Log out</button>
    </template>
  </AuthCard>
</template>
