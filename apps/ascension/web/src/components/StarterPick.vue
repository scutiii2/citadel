<script setup lang="ts">
import { computed, ref } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { useAscensionStore } from "../stores/ascension";
import { ascendedStats } from "../utils/ascension";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmPickCard from "./ui/EmPickCard.vue";
import { starterCopy } from "./starterCopy";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPageHead from "./ui/EmPageHead.vue";

/** New game: pick the first Ascended from a row of preview cards (the chosen one has the
 * copper outline), then start with it. The first starter is chosen on open. "Main menu" goes back. */
const emit = defineEmits<{ back: []; started: [] }>();
defineProps<{ hideHeading?: boolean }>();

const store = useAscensionStore();
const picked = ref<string | null>(null);
const starters = computed(() => (store.catalog?.ascendeds ?? []).filter((s) => s.starter));
/** The first starter shows until another is chosen, so the big card is never empty. */
const current = computed(() => starters.value.find((s) => s.id === picked.value) ?? starters.value[0] ?? null);
const statsOf = (s: AscendedInfo) => ascendedStats(s, 1, store.catalog?.tiers.find((t) => t.id === s.start_tier)?.stat_multiplier ?? 1);

function pick(id: string): void {
  if (!store.busy) picked.value = id;
}

async function start(): Promise<void> {
  if (current.value === null) return;
  if ((await store.createProfile(current.value.id)) !== null) emit("started");
}
</script>

<template>
  <section class="starters">
    <EmPageHead v-if="!hideHeading" title="Choose your first Ascended" subtitle="One companion. A whole world of possibilities.">
      <button type="button" class="back" @click="emit('back')"><EmIcon name="arrow" class="back-arrow" /> Main menu</button>
    </EmPageHead>

    <div v-if="current" class="picker">
      <div class="choices" role="radiogroup" aria-label="Starter Ascended">
        <div v-for="s in starters" :key="s.id" class="item">
          <EmPickCard
            :selected="current.id === s.id"
            :disabled="store.busy"
            :aria-label="s.name"
            @select="pick(s.id)"
          >
            <AscendedPreviewCard :ascended="s" :tier-id="s.start_tier" :stars="0" :stats="statsOf(s)" show-level />
          </EmPickCard>
          <p class="note">
            {{ starterCopy(s.id).motto }}
          </p>
        </div>
      </div>

      <EmButton variant="primary" class="start" :disabled="store.busy" @click="start">
        <EmIcon name="play" /> Start with {{ current.name }}
      </EmButton>
    </div>
    <p v-else class="empty">No starters available.</p>
  </section>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: var(--em-target);
  padding: 0 4px;
  border: 0;
  color: var(--em-accent);
  background: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.back-arrow { transform: scaleX(-1); }
.picker { display: flex; flex-direction: column; gap: var(--em-space-6); }
.choices { display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--em-preview-card-width), 220px)); gap: 18px; justify-content: center; }
.item { min-width: 0; --card-width: 100%; }
.note { padding: 9px 6px; margin: 0; text-align: center; font-size: 12px; color: var(--em-muted); border-bottom: 1px solid var(--em-accent-edge); }
.start { align-self: center; width: min(320px, 100%); }
.empty { color: var(--em-muted); }
@media (max-width: 600px) { .choices { grid-template-columns: repeat(auto-fit, minmax(var(--em-preview-card-width), 1fr)); } }
</style>
