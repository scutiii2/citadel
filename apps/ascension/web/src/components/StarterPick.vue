<script setup lang="ts">
import { computed, ref } from "vue";
import { useAscensionStore } from "../stores/ascension";
import { abilityEffect } from "../utils/ascension";
import AscendedTemplateCard from "./AscendedTemplateCard.vue";
import AscendedPreviewCard from "./AscendedPreviewCard.vue";
import EmPickCard from "./ui/EmPickCard.vue";
import { starterCopy } from "./starterCopy";
import EmButton from "./ui/EmButton.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPageHead from "./ui/EmPageHead.vue";
import EmPanel from "./ui/EmPanel.vue";
import type { IconName } from "./ui/icons";

/** New game: pick the first Ascended from a column of small cards (the chosen one has the
 * copper outline and says "Selected"); the large card and a side panel show the chosen
 * Ascended in full. The first starter is chosen on open. "Main menu" goes back. */
const emit = defineEmits<{ back: []; started: [] }>();
defineProps<{ hideHeading?: boolean }>();

const CATEGORY_ICONS: Record<string, IconName> = { ATTACK: "sword", DEFENSE: "shield", SUPPORT: "arrow", FLEE: "arrow", INTERCEPT: "ascended" };

const store = useAscensionStore();
const picked = ref<string | null>(null);
const starters = computed(() => (store.catalog?.ascendeds ?? []).filter((s) => s.starter));
/** The first starter shows until another is chosen, so the big card is never empty. */
const current = computed(() => starters.value.find((s) => s.id === picked.value) ?? starters.value[0] ?? null);
const copy = computed(() => starterCopy(current.value?.id ?? ""));
const hp = computed(() => ({ base: current.value?.base.hp ?? 0, growth: current.value?.growth.hp ?? 0 }));
const firstAbility = computed(() => current.value?.abilities[0] ?? null);
const unlockLevels = computed(() => (current.value?.abilities ?? []).map((a) => a.unlock_level));

function unlockText(levels: number[]): string {
  if (levels.length === 0) return "";
  const head = levels.slice(0, -1).join(", ");
  return levels.length === 1 ? `${levels[0]}` : `${head} and ${levels[levels.length - 1]}`;
}

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
            <AscendedPreviewCard :ascended="s" />
          </EmPickCard>
          <p class="note">
            {{ starterCopy(s.id).motto }}
          </p>
        </div>
      </div>

      <AscendedTemplateCard :ascended="current" class="detail" />

      <EmPanel class="info">
        <p class="em-eyebrow">Your chosen starter</p>
        <h3 class="em-pixel name">{{ current.name }}</h3>
        <p class="blurb">{{ copy.blurb }}</p>
        <div class="facts">
          <div>
            <strong><EmIcon name="heart" /> Health</strong>
            <p class="em-num">{{ hp.base }} HP · +{{ hp.growth }} / lvl</p>
          </div>
          <div v-if="firstAbility">
            <strong><EmIcon :name="CATEGORY_ICONS[firstAbility.category] ?? 'ascended'" /> {{ firstAbility.name }}</strong>
            <p>{{ abilityEffect(firstAbility) }}</p>
          </div>
          <div>
            <strong><EmIcon name="flame" /> Grow together</strong>
            <p>Abilities unlock at levels {{ unlockText(unlockLevels) }}.</p>
          </div>
        </div>
        <EmButton variant="primary" class="start" :disabled="store.busy" @click="start">
          <EmIcon name="play" /> Start with {{ current.name }}
        </EmButton>
        <button type="button" class="back-link" @click="emit('back')"><EmIcon name="arrow" class="back-arrow" /> Back to main menu</button>
      </EmPanel>
    </div>
    <p v-else class="empty">No starters available.</p>
  </section>
</template>

<style scoped>
.back,
.back-link {
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
.back-arrow {
  transform: scaleX(-1);
}
.picker {
  display: grid;
  grid-template-columns: 190px 440px minmax(0, 1fr);
  gap: var(--em-space-6);
  align-items: start;
}
.choices {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.item {
  --card-width: 170px;
}
.note {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--em-muted);
}
.name {
  margin: 16px 0 12px;
  font-size: 18px;
  line-height: 1.4;
}
.blurb {
  color: var(--em-muted);
}
.facts {
  display: grid;
  gap: 18px;
  margin: 24px 0;
}
.facts > div {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--em-divider);
}
.facts strong {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
  font-size: 16px;
}
.facts p {
  color: var(--em-muted);
}
.start {
  width: 100%;
}
.back-link {
  margin-top: 12px;
}
.empty {
  color: var(--em-muted);
}
@media (max-width: 1100px) {
  .picker {
    grid-template-columns: 190px minmax(0, 1fr);
  }
  .info {
    grid-column: 1 / -1;
  }
}
@media (max-width: 700px) {
  .picker {
    display: flex;
    flex-direction: column;
    gap: 28px;
  }
  .choices {
    width: 100%;
    gap: 18px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 16px;
    --card-width: 150px;
  }
  .note {
    margin-top: 0;
  }
  .detail {
    --card-width: min(440px, 100%);
    align-self: center;
  }
}
</style>
