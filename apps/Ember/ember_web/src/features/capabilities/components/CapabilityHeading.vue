<script setup lang="ts">
import { CAPABILITY_ICONS } from "../utils/capabilityIcons";

/** The left part of a capability's row, shared by the Capabilities cards and the Supermarket rows: an icon
 * tile (with a status dot on its corner), the name over its tool id, an optional problem line, and the
 * summary pill. It renders four siblings, so the parent's flex row lays them out. */
defineProps<{
  label: string;
  name: string;
  /** What it brings, or why it brings nothing. */
  summary: string;
  /** The tile's picture: a built-in capability, an extension, or the other tools. None: no tile. */
  icon?: "builtin" | "extension" | "other";
  /** The dot on the tile's corner (or alone, with no tile); none for a group that is not a real item. */
  status?: "ok" | "bad" | "off";
  /** The summary is a problem (an extension that is not connected). */
  problem?: boolean;
  /** A line under the name (why an extension cannot be reached). */
  detail?: string;
}>();
</script>

<template>
  <span v-if="icon" class="tile" aria-hidden="true">
    <svg viewBox="0 0 16 16" width="18" height="18"><path :d="CAPABILITY_ICONS[icon]" /></svg>
    <span v-if="status" :class="['dot', status]" />
  </span>
  <span v-else-if="status" :class="['dot', 'inline', status]" aria-hidden="true" />
  <span class="heading">
    <h3>{{ label }}</h3>
    <code class="name">{{ name }}</code>
    <span v-if="detail" class="detail">{{ detail }}</span>
  </span>
  <span :class="['summary', problem ? 'bad' : 'muted']">{{ summary }}</span>
</template>

<style scoped>
.tile {
  position: relative;
  display: grid;
  flex: none;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-md);
  background: var(--bg);
}
.tile svg {
  fill: none;
  stroke: var(--accent);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.tile .dot {
  position: absolute;
  right: -3px;
  bottom: -3px;
  border: 2px solid var(--surface);
  box-sizing: content-box;
}
.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
}
.dot.ok {
  background: var(--success);
}
.dot.bad {
  background: var(--danger);
}
.dot.off {
  background: var(--muted);
}
.heading {
  display: flex;
  flex: 1 1 140px;
  flex-direction: column;
  min-width: 0;
}
h3 {
  margin: 0;
  font-size: 1em;
}
.name {
  font-family: var(--mono);
  font-size: 0.8em;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.detail {
  font-size: 0.8em;
  color: var(--danger);
  overflow-wrap: anywhere;
}
.summary {
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 0.75em;
  white-space: nowrap;
  background: var(--bg);
}
.muted {
  color: var(--muted);
}
.bad {
  color: var(--danger);
}
</style>
