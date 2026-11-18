import { defineStore } from "pinia";
import { ref } from "vue";
import { apiRequest } from "../api/http";

type RequiredTool = "bard" | "scribe" | "reader";
type Status = Partial<Record<RequiredTool, { ready: boolean; reason: string | null }>>;

export const useToolConnectionsStore = defineStore("toolConnections", () => {
  const status = ref<Status>({});
  let pending: Promise<void> | undefined;

  function refresh(): Promise<void> {
    // Multiple chat mounts share the current fetch. Older servers can still answer feature calls.
    return pending ??= apiRequest<Status>("GET", "/api/connection-status")
      .then(result => { status.value = result; })
      .catch(() => { status.value = {}; })
      .finally(() => { pending = undefined; });
  }

  function reason(tool: RequiredTool): string | null {
    const connection = status.value[tool];
    return connection?.ready === false ? connection.reason : null;
  }

  return { status, refresh, reason };
});
