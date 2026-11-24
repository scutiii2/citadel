<script setup lang="ts">
import { RouterLink } from "vue-router";
import ThemeSelect from "./ThemeSelect.vue";

/** The Profile popover's content: identity, the personal pages, theme and Log out.
 * The header owns opening, Escape and focus return. */
defineProps<{ username: string; email: string }>();
const emit = defineEmits<{ logout: []; navigate: [] }>();
</script>

<template>
  <div class="account-menu">
    <div class="identity"><strong>{{ username }}</strong><span>{{ email }}</span></div>
    <nav aria-label="Account pages">
      <RouterLink to="/profile" @click="emit('navigate')">Profile</RouterLink>
    </nav>
    <ThemeSelect />
    <button type="button" class="chip logout" @click="emit('logout')">Log out</button>
  </div>
</template>

<style scoped>
.account-menu { display: grid; gap: 10px; }
.identity { display: grid; gap: 2px; min-width: 0; }
.identity span { color: var(--muted); font-size: 0.8rem; overflow-wrap: anywhere; }
nav { display: grid; gap: 2px; }
nav a { display: block; padding: 8px; border-radius: var(--radius-md); color: var(--text); text-decoration: none; font-size: 0.88rem; }
nav a:hover { background: var(--surface); }
nav a.router-link-exact-active { box-shadow: inset 2px 0 var(--accent); }
nav a:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
@media (max-width: 767px) { nav a { min-height: 44px; display: flex; align-items: center; } }
</style>
