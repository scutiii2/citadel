import { defineStore } from "pinia";
import { ref } from "vue";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import { errorMessage } from "../utils/errors";

/** Whether Treasury answers. The header Notifications, Overview and Instances share this one result. */
export const useNoticesStore = defineStore("notices", () => {
  /** null until the first check; false when Treasury did not answer. */
  const reachable = ref<boolean | null>(null);
  const error = ref("");
  const loading = ref(false);

  async function refresh(): Promise<void> {
    loading.value = true;
    error.value = "";
    try {
      reachable.value = (await treasuryAdminClient.get()).reachable;
    } catch (err) {
      reachable.value = null;
      error.value = errorMessage(err);
    } finally {
      loading.value = false;
    }
  }

  /** Lets a page that already read the Treasury view report what it saw. */
  function report(value: boolean): void {
    reachable.value = value;
    error.value = "";
  }

  return { reachable, error, loading, refresh, report };
});
