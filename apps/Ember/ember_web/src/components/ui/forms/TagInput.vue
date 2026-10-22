<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from "vue";

/** Tag chips with a text box and a list of tags to pick from (a combobox, not the browser's
 * <datalist>). Enter or a comma adds what is typed; ArrowUp and ArrowDown walk the list and
 * Enter takes the highlighted one; Esc closes the list; Backspace in an empty box removes the
 * last tag. The owner supplies the rules (`normalize`, `max`) and the tags worth suggesting
 * (`known`, most used first). What is typed but not added yet is `v-model:text`, so the owner
 * can treat it as an unsaved edit and ask for `commit()` before it saves. */

const props = withDefaults(
  defineProps<{
    /** Tags the user already has elsewhere, most used first; ones already chosen are not offered. */
    known?: { tag: string; count: number }[];
    /** Cleans what was typed into a tag; "" means nothing usable was left. */
    normalize: (raw: string) => string;
    max: number;
    maxLength: number;
    disabled?: boolean;
    /** Names the chip list; the text box is "Add a tag". */
    label?: string;
  }>(),
  { known: () => [], disabled: false, label: "Tags" },
);

const tags = defineModel<string[]>({ required: true });
const text = defineModel<string>("text", { default: "" });
// The parent updates its copy at once but this component's `tags` only after the next render, so a
// second change in the same tick (commit() then add()) must start from what was just set.
const current = ref<string[]>([...tags.value]);
watch(tags, (v) => (current.value = [...v]));
function setTags(next: string[]): void {
  current.value = next;
  tags.value = next;
}

const listId = useId();
const root = ref<HTMLElement | null>(null);
const open = ref(false);
const highlighted = ref(-1);
const error = ref("");

// What is typed, as the tag it would become, so "work st" finds "work-stuff".
const query = computed(() => text.value.trim().toLowerCase().replace(/\s+/g, "-"));
const options = computed(() =>
  props.known.filter((k) => !current.value.includes(k.tag) && (query.value === "" || k.tag.includes(query.value))),
);
const listVisible = computed(() => open.value && options.value.length > 0 && !props.disabled);
const optionId = (i: number) => `${listId}-option-${i}`;

watch(options, () => {
  highlighted.value = -1;
});
watch(highlighted, async (i) => {
  if (i < 0) return;
  await nextTick();
  root.value?.querySelectorAll("[role=option]")[i]?.scrollIntoView?.({ block: "nearest" });
});

/** Adds a tag. False when it is refused (too many); a repeat counts as added. */
function add(tag: string): boolean {
  if (current.value.includes(tag)) return true;
  if (current.value.length >= props.max) {
    error.value = `A note can have at most ${props.max} tags.`;
    return false;
  }
  setTags([...current.value, tag]);
  error.value = "";
  return true;
}

/** Moves what is typed into the chips. */
function commit(): void {
  if (text.value.trim() === "") {
    text.value = "";
    return;
  }
  const tag = props.normalize(text.value);
  if (tag === "") {
    error.value = "A tag needs letters or digits.";
    text.value = "";
  } else if (add(tag)) {
    text.value = "";
  }
}

function pick(tag: string): void {
  if (add(tag)) text.value = "";
  highlighted.value = -1;
}

function remove(tag: string): void {
  setTags(current.value.filter((t) => t !== tag));
  error.value = "";
}

function onKey(event: KeyboardEvent): void {
  if (event.isComposing || event.keyCode === 229) return;
  const last = options.value.length - 1;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    if (options.value.length === 0) return;
    event.preventDefault();
    if (!open.value) {
      open.value = true;
      return;
    }
    const step = event.key === "ArrowDown" ? 1 : -1;
    highlighted.value = highlighted.value === -1 ? (step === 1 ? 0 : last) : (highlighted.value + step + options.value.length) % options.value.length;
  } else if (event.key === "Enter") {
    event.preventDefault(); // Enter must not submit the form around this box
    const chosen = listVisible.value ? options.value[highlighted.value] : undefined;
    if (chosen) pick(chosen.tag);
    else commit();
  } else if (event.key === ",") {
    event.preventDefault();
    commit();
  } else if (event.key === "Escape" && listVisible.value) {
    event.preventDefault();
    event.stopPropagation();
    open.value = false;
  } else if (event.key === "Backspace" && text.value === "" && current.value.length > 0) {
    setTags(current.value.slice(0, -1));
  }
}

function onBlur(): void {
  commit();
  open.value = false;
}

defineExpose({ commit, add });
</script>

<template>
  <div ref="root" class="tag-input">
    <ul v-if="tags.length" class="tag-list" :aria-label="label">
      <li v-for="tag in tags" :key="tag" class="tag">
        {{ tag }}
        <button type="button" :aria-label="`Remove tag ${tag}`" :disabled="disabled" @click="remove(tag)">×</button>
      </li>
    </ul>
    <div class="combo">
      <input
        v-model="text"
        type="text"
        role="combobox"
        autocomplete="off"
        aria-label="Add a tag"
        :aria-invalid="!!error"
        :aria-describedby="error ? `${listId}-error` : undefined"
        aria-autocomplete="list"
        :aria-expanded="listVisible"
        :aria-controls="listId"
        :aria-activedescendant="listVisible && highlighted >= 0 ? optionId(highlighted) : undefined"
        placeholder="Add a tag, then press Enter"
        :maxlength="maxLength * 2"
        :disabled="disabled"
        @focus="open = true"
        @input="open = true"
        @keydown="onKey"
        @blur="onBlur"
      />
      <ul v-show="listVisible" :id="listId" class="options" role="listbox" aria-label="Your tags">
        <li
          v-for="(option, i) in options"
          :id="optionId(i)"
          :key="option.tag"
          role="option"
          :aria-selected="i === highlighted"
          :class="{ active: i === highlighted }"
          @mousedown.prevent="pick(option.tag)"
          @mousemove="highlighted = i"
        >
          <span class="name">{{ option.tag }}</span>
          <span class="count">{{ option.count }} {{ option.count === 1 ? "note" : "notes" }}</span>
        </li>
      </ul>
    </div>
    <p v-if="error" :id="`${listId}-error`" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.tag-input {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  color: var(--text);
  background: var(--bg);
  font-size: 0.8em;
}
.tag button {
  padding: 0;
  border: none;
  color: var(--muted);
  background: none;
  font: inherit;
  line-height: 1;
  cursor: pointer;
}
.tag button:hover:not(:disabled) {
  color: var(--danger);
}
.combo {
  position: relative;
}
.combo input {
  width: 100%;
}
.options {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  z-index: 16;
  max-height: 200px;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
}
.options li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.9em;
}
.options li.active {
  /* --bg on the --surface popup is barely different; the accent tint shows in both themes. */
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  box-shadow: inset 3px 0 var(--accent);
}
.options .count {
  color: var(--muted);
  font-size: 0.85em;
  white-space: nowrap;
}
@media (pointer: coarse), (max-width: 767px) {
  .tag button { min-width: 44px; min-height: 44px; }
}
</style>
