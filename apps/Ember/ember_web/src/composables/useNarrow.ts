import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/** True while the viewport is under 768px, where the CSS stacks panes and the
 * page swaps its tab roles. Follows resizes while the component is mounted. */
export function useNarrow(): Ref<boolean> {
  const query = window.matchMedia?.("(max-width: 767px)");
  const narrow = ref(query?.matches ?? false);
  const update = (event: MediaQueryListEvent): void => { narrow.value = event.matches; };
  onMounted(() => query?.addEventListener?.("change", update));
  onBeforeUnmount(() => query?.removeEventListener?.("change", update));
  return narrow;
}
