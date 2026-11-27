import { onBeforeUnmount, ref, watch, type Ref } from "vue";
import { isDesktop, mediaUrl } from "../utils/server";

/** A URL an `<img>` can load for a picture that is either still a local file or one the server stored.
 * Never takes a URL from message text: a stored picture is named by its bounded file id only. */
export function useImagePreview(source: () => File | string | undefined): { url: Ref<string>; failed: Ref<boolean> } {
  const url = ref("");
  const failed = ref(false);
  let run = 0; // a late answer for a source that has since changed is dropped

  function release(): void {
    if (url.value.startsWith("blob:")) URL.revokeObjectURL(url.value);
    url.value = "";
  }

  watch(source, async (value) => {
    const current = ++run;
    release();
    failed.value = false;
    if (!value) return;
    if (typeof value !== "string") {
      url.value = URL.createObjectURL(value);
      return;
    }
    const path = `/api/attachments/files/${value}/content`;
    // Browser: the path itself (cookie). Windows app: a blob: URL fetched with the bearer.
    if (!isDesktop()) {
      url.value = path;
      return;
    }
    try {
      const fetched = await mediaUrl(path);
      if (current === run) url.value = fetched;
      else URL.revokeObjectURL(fetched);
    } catch {
      if (current === run) failed.value = true;
    }
  }, { immediate: true });
  onBeforeUnmount(() => {
    run++;
    release();
  });

  return { url, failed };
}
