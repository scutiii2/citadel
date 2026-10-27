import { getCurrentInstance, onMounted, onUnmounted, ref, type Ref } from "vue";
import { onBeforeRouteLeave, routerKey, type RouteLocationNormalized } from "vue-router";

export interface UnsavedGuardOptions {
  /** There are edits to lose: leaving asks first. */
  dirty: () => boolean;
  /** A save or delete is running: leaving the route is refused, and closing the tab warns. */
  busy?: () => boolean;
  /** Routes that keep the page's state (e.g. another tab of the same page) leave without asking. */
  allow?: (to: RouteLocationNormalized) => boolean;
  /** Runs when a route change starts asking, before `open` turns true. */
  onAsk?: () => void;
}

export interface UnsavedGuard {
  /** True while the discard dialog is up; the page binds its ConfirmModal to it. */
  open: Ref<boolean>;
  /** The dialog's answer: true discards and lets the route change go on. */
  answer: (discard: boolean) => void;
}

/** Leaving a page with unsaved edits asks first: a route change waits on the page's discard dialog
 * (`open` / `answer`), and closing or reloading the tab gets the browser's own warning. A mount without a
 * router (unit tests) skips the route part. An answer still pending when the page unmounts counts as "stay". */
export function useUnsavedGuard(options: UnsavedGuardOptions): UnsavedGuard {
  const open = ref(false);
  let pending: ((discard: boolean) => void) | null = null;
  const busy = (): boolean => options.busy?.() ?? false;

  function answer(discard: boolean): void {
    open.value = false;
    pending?.(discard);
    pending = null;
  }

  if (getCurrentInstance()?.appContext.provides[routerKey as symbol]) {
    onBeforeRouteLeave((to) => {
      if (options.allow?.(to)) return true;
      if (busy()) return false;
      if (!options.dirty()) return true;
      options.onAsk?.();
      open.value = true;
      return new Promise<boolean>((resolve) => { pending = resolve; });
    });
  }

  function beforeUnload(event: BeforeUnloadEvent): void {
    if (options.dirty() || busy()) {
      event.preventDefault();
      event.returnValue = "";
    }
  }
  onMounted(() => window.addEventListener("beforeunload", beforeUnload));
  onUnmounted(() => {
    window.removeEventListener("beforeunload", beforeUnload);
    answer(false);
  });

  return { open, answer };
}
