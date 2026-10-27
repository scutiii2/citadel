<script setup lang="ts">
// The rail's account button and the menu it opens: the account's email, then
// Usage, Settings, Profile, the theme switch, Ember Admin (for admins) and Log out.
// It closes on Esc, a press outside, a route change or a choice; arrow keys move
// between the rows.
import { nextTick, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useOutsideClose } from "../../composables/useOutsideClose";
import { useTheme } from "../../composables/useTheme";
import { PROFILE_ICON, type NavPage } from "../../router/pages";

defineProps<{
  username: string;
  email: string;
  /** Page rows listed first, in groups with a divider between them. */
  groups: NavPage[][];
  /** Ember Admin's address, or null when the account may not open it. */
  adminUrl: string | null;
}>();
const emit = defineEmits<{ logout: [] }>();

const THEME_LABELS = { system: "System", light: "Light", dark: "Dark" } as const;
const { theme, cycle } = useTheme();

const route = useRoute();
const open = ref(false);
const root = ref<HTMLElement | null>(null);
const trigger = ref<HTMLButtonElement | null>(null);

const items = (): HTMLElement[] => [...(root.value?.querySelectorAll<HTMLElement>("[role='menuitem']") ?? [])];

async function show(): Promise<void> {
  open.value = true;
  await nextTick();
  items()[0]?.focus();
}

function close(refocus = false): void {
  if (!open.value) return;
  open.value = false;
  if (refocus) void nextTick(() => trigger.value?.focus());
}

function toggle(): void {
  if (open.value) close();
  else void show();
}

function move(step: 1 | -1 | "first" | "last"): void {
  const all = items();
  if (all.length === 0) return;
  const at = all.indexOf(document.activeElement as HTMLElement);
  let next: number;
  if (step === "first") next = 0;
  else if (step === "last") next = all.length - 1;
  else if (at < 0) next = step === 1 ? 0 : all.length - 1;
  else next = (at + step + all.length) % all.length;
  all[next]!.focus();
}

function onKey(event: KeyboardEvent): void {
  const steps: Record<string, 1 | -1 | "first" | "last"> = { ArrowDown: 1, ArrowUp: -1, Home: "first", End: "last" };
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    close(true);
  } else if (event.key in steps) {
    event.preventDefault();
    move(steps[event.key]!);
  } else if (event.key === "Tab") {
    close();
  }
}

/** A capability's own page keeps Capabilities marked. */
const isCurrent = (to: string): boolean => to === "/capabilities" && route.name === "capability-page";

function logout(): void {
  close();
  emit("logout");
}

watch(() => route.fullPath, () => close());
useOutsideClose(root, open, () => close());
</script>

<template>
  <div ref="root" class="account-menu" @keydown="onKey">
    <button
      ref="trigger"
      type="button"
      class="account"
      :title="username"
      :aria-label="`${username} - account menu`"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle"
    >
      {{ username.charAt(0).toUpperCase() }}
    </button>

    <div v-if="open" class="menu" role="menu" :aria-label="`${username} - account menu`">
      <div class="email" role="presentation">{{ email }}</div>

      <template v-for="(group, i) in groups" :key="i">
        <hr v-if="i > 0" role="separator" />
        <RouterLink v-for="p in group" :key="p.to" :to="p.to" class="row" :class="{ current: isCurrent(p.to) }" role="menuitem">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in p.icon" :key="d" :d="d" /></svg>
          <span>{{ p.label }}</span>
        </RouterLink>
      </template>
      <hr v-if="groups.length" role="separator" />
      <RouterLink to="/account" class="row" role="menuitem">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in PROFILE_ICON" :key="d" :d="d" /></svg>
        <span>Profile</span>
      </RouterLink>
      <button type="button" class="row theme-row" role="menuitem" @click="cycle">
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
        <span>Theme</span>
        <span class="value">{{ THEME_LABELS[theme] }}</span>
      </button>
      <a v-if="adminUrl" :href="adminUrl" target="_blank" rel="noopener noreferrer" class="row admin-link" role="menuitem" @click="close()">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 3 3 7v5c0 5 5 8 9 10 4-2 9-5 9-10V7zM8 12l3 3 5-6" /></svg>
        <span>Ember Admin</span>
        <svg class="value" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>
      </a>

      <hr role="separator" />
      <button type="button" class="row logout" role="menuitem" @click="logout">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
        </svg>
        <span>Log out</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.account-menu {
  position: relative;
}
.account {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.85em;
  font-weight: 600;
  color: var(--muted);
  background: transparent;
}
.account:hover,
.account[aria-expanded='true'] {
  color: var(--text);
  background: var(--bg);
}
.menu {
  position: absolute;
  z-index: 40;
  left: calc(100% + 8px);
  bottom: 0;
  width: 240px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 24px rgb(0 0 0 / 22%);
}
.email {
  padding: 8px 10px 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--muted);
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  text-decoration: none;
  font: inherit;
  font-size: 0.9em;
  color: var(--text);
  background: transparent;
}
.row:hover,
.row:focus-visible {
  outline: none;
  background: var(--bg);
}
.row.router-link-exact-active,
.row.current {
  box-shadow: inset 2px 0 0 var(--accent);
}
.value {
  margin-left: auto;
  font-size: 0.8rem;
  color: var(--muted);
}
hr {
  margin: 4px 6px;
  border: none;
  border-top: 1px solid var(--border);
}
svg {
  flex-shrink: 0;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
</style>
