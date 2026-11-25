<script setup lang="ts">
import { AuthCard } from "@citadel/ui";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>

<template>
  <AuthCard
    title="No access"
    subtitle="Treasury administration needs settings.manage. Ask an admin to give your account a role that has it, and verify your email in Ember."
  >
    <button type="button" @click="auth.logout()">Log out</button>
  </AuthCard>
</template>
