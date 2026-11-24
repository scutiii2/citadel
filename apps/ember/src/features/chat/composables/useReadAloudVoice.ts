import { computed, ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { readStored, writeStored } from "../../../utils/browser/storage";

const key = (accountId: number) => `ember_web.readAloudVoice.${accountId}`;
const stored = ref("");

/** The voice read aloud uses without asking, kept per account on this device. Empty means ask every time. */
export function useReadAloudVoice() {
  const auth = useAuthStore();
  const load = () => {
    const id = auth.account?.id ?? null;
    stored.value = id === null ? "" : readStored(key(id)) ?? "";
  };
  load();
  watch(() => auth.account?.id, load);
  const voice = computed({
    get: () => stored.value,
    set: (name: string) => {
      stored.value = name;
      if (auth.account) writeStored(key(auth.account.id), name);
    },
  });
  return { voice };
}
