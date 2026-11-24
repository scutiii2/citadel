<script setup lang="ts">
import type { Theme } from "../../composables/useTheme";

defineProps<{ theme: Theme }>();
</script>

<template>
  <svg v-if="theme === 'light'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" />
  </svg>
  <svg v-else-if="theme === 'dark'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
  </svg>
  <svg v-else viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </svg>
</template>
