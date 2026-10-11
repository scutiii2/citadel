import { defineStore } from "pinia";
import { ref, shallowRef, type Ref } from "vue";
import type { HostBridge } from "../host/HostBridge";
import type { AscensionClient } from "../api/AscensionClient";

type SessionStatus = "connecting" | "ready" | "no-ticket" | "failed" | "ended";

/** Lifecycle behavior uses injected state and bridge, owned by one Pinia instance. */
class SessionController {
  private readonly bridge: Ref<HostBridge | null>;
  private readonly status: Ref<SessionStatus>;
  private readonly revision: Ref<number>;
  constructor(bridge: Ref<HostBridge | null>, status: Ref<SessionStatus>, revision: Ref<number>) {
    this.bridge = bridge; this.status = status; this.revision = revision;
  }
  async connect(): Promise<void> {
    if (!this.bridge.value || this.status.value === "ready" || this.status.value === "ended") return;
    const started = this.revision.value;
    this.status.value = "connecting";
    const result = await this.bridge.value.connect();
    if (started === this.revision.value) this.status.value = result;
  }
  end(): void {
    this.bridge.value?.endSession(); this.status.value = "ended"; this.revision.value += 1;
  }
}

export const useSessionStore = defineStore("game-session", () => {
  const bridge = shallowRef<HostBridge | null>(null);
  const client = shallowRef<AscensionClient | null>(null);
  const status = ref<SessionStatus>("no-ticket");
  const revision = ref(0);
  const controller = new SessionController(bridge, status, revision);
  return { bridge, client, status, revision, connect: controller.connect.bind(controller), end: controller.end.bind(controller) };
});
