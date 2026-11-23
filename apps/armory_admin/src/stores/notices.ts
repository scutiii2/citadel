import { defineStore } from "pinia";
import { ref } from "vue";
import { capabilitiesAdminClient } from "../api/CapabilitiesAdminClient";
import { useAuthStore } from "./auth";

/** Whether Armory answers. The header Notifications, Overview and Capabilities share this one result. */
export const useNoticesStore = defineStore("notices", () => {
  /** null until the first check (or when the account may not check); false when Armory did not answer. */
  const reachable = ref<boolean | null>(null);
  const error = ref(""); // kept for the shared header; Armory reports only reachable or not
  const loading = ref(false);

  async function refresh(): Promise<void> {
    if (!useAuthStore().hasPermission("capabilities.manage")) return;
    loading.value = true;
    error.value = "";
    try {
      await capabilitiesAdminClient.list();
      reachable.value = true;
    } catch {
      reachable.value = false;
    } finally {
      loading.value = false;
    }
  }

  /** Lets a page that already read from Armory report what it saw. */
  function report(value: boolean): void {
    reachable.value = value;
    error.value = "";
  }

  return { reachable, error, loading, refresh, report };
});
