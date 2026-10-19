<script setup lang="ts">
// The rail's account button and the menu it opens: the account's email, then
// Profile, Settings, the theme switch and Log out. It closes on Esc, a press
// outside, a route change or a choice; arrow keys move between the rows.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { useTheme } from "../composables/useTheme";

defineProps<{ username: string; email: string }>();
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

function onPointerDown(event: Event): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) close();
}

function logout(): void {
  close();
  emit("logout");
}

watch(() => route.fullPath, () => close());
onMounted(() => document.addEventListener("pointerdown", onPointerDown));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onPointerDown));
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

      <RouterLink to="/profile" class="row" role="menuitem">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M20 21v-2a7 7 0 0 0-14 0v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0" /></svg>
        <span>Profile</span>
      </RouterLink>
      <RouterLink to="/settings" class="row" role="menuitem">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" />
          <path d="m9 3-.6 2.4-2 .9-2.3-.7-2 3.4 1.7 1.8v2.4L2.1 15l2 3.4 2.3-.7 2 .9L9 21h6l.6-2.4 2-.9 2.3.7 2-3.4-1.7-1.8v-2.4L21.9 9l-2-3.4-2.3.7-2-.9L15 3z" />
        </svg>
        <span>Settings</span>
      </RouterLink>
      <button type="button" class="row theme-row" role="menuitem" @click="cycle">
        <svg v-if="theme === 'light'" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
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
  height: auto;
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
.row.router-link-exact-active {
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
/* The bottom bar: open the menu upward, aligned to the right edge. */
@media (max-width: 767px) {
  .account {
    width: 44px;
    height: 44px;
  }
  .menu {
    left: auto;
    right: 0;
    bottom: calc(100% + 8px);
  }
}
</style>
