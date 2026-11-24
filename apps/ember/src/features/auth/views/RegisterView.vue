<script setup lang="ts">
import PasswordInput from "../../../components/ui/forms/PasswordInput.vue";
import { reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import AuthCard from "../../../components/auth/AuthCard.vue";
import { errorMessage } from "../../../utils/errors";
import { useAuthStore } from "../../../stores/auth";

const auth = useAuthStore();
const router = useRouter();

const form = reactive({ username: "", email: "", password: "", invite_code: "" });
const error = ref("");
const busy = ref(false);

async function submit(): Promise<void> {
  if (busy.value) return;
  error.value = "";
  busy.value = true;
  try {
    await auth.register({
      username: form.username.trim(),
      email: form.email.trim(),
      password: form.password,
      invite_code: form.invite_code.trim(),
    });
    form.password = "";
    form.invite_code = "";
    await router.replace({ name: "chat" });
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthCard title="Create an account" subtitle="Registration needs an invite code sent to your email.">
    <form @submit.prevent="submit">
      <label>
        Invite code
        <input v-model="form.invite_code" autocomplete="off" spellcheck="false" required autofocus />
      </label>
      <label>
        Username
        <input
          v-model="form.username"
          autocomplete="username"
          minlength="3"
          maxlength="80"
          pattern="[A-Za-z0-9_.\-]+"
          title="Letters, digits, dot, dash and underscore"
          required
        />
      </label>
      <label>
        Email
        <input v-model="form.email" type="email" autocomplete="email" aria-describedby="invite-email-hint" required />
      </label>
      <p id="invite-email-hint" class="notice">Use the email address the invite was sent to.</p>
      <PasswordInput label="Password" v-model="form.password" autocomplete="new-password" minlength="8" required />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" :disabled="busy" :aria-busy="busy">{{ busy ? "Creating ..." : "Create account" }}</button>
    </form>
    <template #footer>Already registered? <RouterLink to="/login">Log in</RouterLink></template>
  </AuthCard>
</template>
