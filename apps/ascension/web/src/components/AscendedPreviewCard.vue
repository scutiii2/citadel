<script setup lang="ts">
import { computed } from "vue";
import type { AscendedInfo } from "../api/AscensionClient";
import { titleCase } from "../utils/ascension";
import { spriteFor } from "../utils/sprites";
import TypeSymbol from "./ui/TypeSymbol.vue";

/** An Ascended's preview card, for lists (collection, squad, shop offers, starter pick).
 * Two faces on one flip: the front is the tier-coloured frame (assets/preview_card/front_<tier>.webp,
 * see-through window) over the Ascended's preview sprite, with its name in the top plate;
 * the back is the tier-coloured ornate frame (back_<tier>.webp) with the Ascension Type
 * symbols in its medallion. The tier is the frame's colour, never written. The faces are
 * drawn at 265 x 371 and the boxes below are in those pixels, turned into percentages, so the
 * card scales with its width (`--card-width`, 150 px). On a device with hover the card turns
 * to its back under the pointer; `flipped` keeps the back showing, without turning to the front on hover
 * (for an Ascended not yet collected, whose art stays hidden). */
const props = withDefaults(defineProps<{ ascended: AscendedInfo; level?: number; tierId?: string; showLevel?: boolean; flipped?: boolean }>(), {
  level: 1,
  tierId: "common",
  showLevel: false,
  flipped: false,
});

const FACE_W = 265;
const FACE_H = 371;

/** A box in face pixels as CSS percentages of the card. */
function box(x0: number, y0: number, x1: number, y1: number): Record<string, string> {
  const pct = (v: number, of: number) => `${(v / of) * 100}%`;
  return { left: pct(x0, FACE_W), top: pct(y0, FACE_H), width: pct(x1 - x0, FACE_W), height: pct(y1 - y0, FACE_H) };
}

/** The name plate at the front's top. */
const HEADER = box(43, 18, 222, 52);
/** The front's see-through window, where the sprite shows. */
const ART = box(29, 57, 236, 332);
/** The back's medallion (a circle of 57 px radius around 132, 153). */
const MEDALLION = box(75, 96, 189, 210);

const FRAMES = import.meta.glob<string>("../assets/preview_card/*.webp", { eager: true, import: "default" });

function frameUrl(side: "front" | "back", tierId: string): string {
  return FRAMES[`../assets/preview_card/${side}_${tierId}.webp`] ?? FRAMES[`../assets/preview_card/${side}_common.webp`]!;
}

/** Symbol edge in cqw by how many types share the medallion. */
function symbolSize(count: number): string {
  if (count <= 1) return "34cqw";
  if (count === 2) return "21cqw";
  return count <= 4 ? "15cqw" : "11cqw";
}

const frontUrl = computed(() => frameUrl("front", props.tierId));
const backUrl = computed(() => frameUrl("back", props.tierId));
const artUrl = computed(() => spriteFor(props.ascended.art, "preview_card"));
const tierVar = computed(() => `var(--em-tier-${props.tierId}, var(--em-tier-common))`);
const types = computed(() => props.ascended.ascension_types);
</script>

<template>
  <article
    class="card"
    :class="[`tier-${tierId}`, { flipped }]"
    :style="{ '--tier': tierVar }"
    :aria-label="`${ascended.name}, ${titleCase(tierId)}, level ${level}`"
  >
    <div class="flipper">
      <div class="face front">
        <div class="art" :style="ART" aria-hidden="true">
          <img v-if="artUrl" class="portrait" :src="artUrl" alt="" draggable="false" />
          <span v-else class="letter">{{ ascended.name.slice(0, 1) }}</span>
        </div>
        <img class="frame" :src="frontUrl" alt="" draggable="false" />
        <header class="header" :style="HEADER">
          <h4 class="ascended-name">{{ ascended.name }}</h4>
          <span v-if="showLevel" class="level">Lv {{ level }}</span>
        </header>
      </div>
      <div class="face back" aria-hidden="true">
        <img class="frame" :src="backUrl" alt="" draggable="false" />
        <div class="types" :style="MEDALLION">
          <TypeSymbol v-for="id in types" :key="id" :type-id="id" :size="symbolSize(types.length)" :flat="types.length > 1" decorative />
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
/* Sizes are in cqw (a percent of the card's width), so the text scales with the card. */
.card {
  container-type: inline-size;
  position: relative;
  width: var(--card-width, 150px);
  aspect-ratio: 265 / 371;
  color: #e8e8ea;
  text-align: left;
  perspective: 900px;
}
.flipper {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
}
/* Callers also use "face" on the card root; only the two internal faces are positioned here. */
.flipper > .face {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
}
.back {
  transform: rotateY(180deg);
}
.frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  user-select: none;
}
.art {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #20242b;
}
.portrait {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  user-select: none;
}
.letter {
  font-size: 34cqw;
  font-weight: 600;
  line-height: 1;
  color: var(--em-accent);
}
.header {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2cqw;
  box-sizing: border-box;
  padding: 0 5cqw;
}
.ascended-name {
  margin: 0;
  overflow: hidden;
  font-size: 6.2cqw;
  font-weight: 600;
  letter-spacing: 0.1cqw;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.level {
  flex: none;
  font-size: 4.8cqw;
  font-weight: 600;
  color: var(--tier);
}
.types {
  position: absolute;
  display: flex;
  flex-wrap: wrap;
  align-content: center;
  align-items: center;
  justify-content: center;
  gap: 1cqw;
  box-sizing: border-box;
  padding: 6cqw;
}

@media (hover: hover) {
  .flipper {
    transition: transform 0.45s ease;
  }
  .card:not(.flipped):hover .flipper {
    transform: rotateY(180deg);
  }
}
.card.flipped .flipper {
  transform: rotateY(180deg);
}
@media (prefers-reduced-motion: reduce) {
  .flipper {
    transition: none;
  }
}
</style>
