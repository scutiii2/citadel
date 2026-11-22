<script setup lang="ts">
import AuthCard from "../components/AuthCard.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>

<template>
  <AuthCard
    title="No access"
    subtitle="Armory administration needs capabilities.manage. Ask an admin to give your account a role that has it, and verify your email in Ember."
  >
    <button type="button" @click="auth.logout()">Log out</button>
  </AuthCard>
</template>
