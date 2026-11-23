import { defineStore } from "pinia";
import { ref } from "vue";
import { ticketsAdminClient } from "../api/TicketsAdminClient";
import { toolServicesClient } from "../api/ToolServicesClient";
import { usageClient } from "../api/UsageClient";
import { usageSettingsClient } from "../api/UsageSettingsClient";
import { useAuthStore } from "./auth";

/** Whether Stronghold answers. The header Notifications, Overview and the pages share this one result. */
export const useNoticesStore = defineStore("notices", () => {
  /** null until the first check (or when the account may not check); false when Stronghold did not answer. */
  const reachable = ref<boolean | null>(null);
  const error = ref(""); // kept for the shared header; Stronghold reports only reachable or not
  const loading = ref(false);

  /** One cheap read, from the first page this account may open. */
  function probe(): (() => Promise<unknown>) | null {
    const auth = useAuthStore();
    if (auth.hasPermission("usage.all.view")) return () => usageClient.allAccounts(1);
    if (auth.hasPermission("tickets.manage")) return () => ticketsAdminClient.stats();
    if (auth.hasPermission("settings.manage")) return () => usageSettingsClient.get();
    if (auth.hasPermission("tool_services.manage")) return () => toolServicesClient.list();
    return null;
  }

  async function refresh(): Promise<void> {
    const run = probe();
    if (!run) return;
    loading.value = true;
    error.value = "";
    try {
      await run();
      reachable.value = true;
    } catch {
      reachable.value = false;
    } finally {
      loading.value = false;
    }
  }

  /** Lets a page that already read from Stronghold report what it saw. */
  function report(value: boolean): void {
    reachable.value = value;
    error.value = "";
  }

  return { reachable, error, loading, refresh, report };
});
