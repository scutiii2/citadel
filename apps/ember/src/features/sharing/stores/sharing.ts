import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { sharingClient, type Block, type Landing, type NewShare, type Share } from "../api/SharingClient";

/** What the account sent, what waits for its answer and whom it blocked, as the server holds them. The text of a
 * share is not kept here (the review dialog asks for it). Everything is private: `forget()` and a change of account
 * drop it, and a reply that arrives after that, or after a newer load, is ignored. Changes show only after the
 * server answered; every success refreshes the lists while the page is open. */
export const useSharingStore = defineStore("sharing", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const inbox = ref<Share[]>([]);
  const sent = ref<Share[]>([]);
  const blocks = ref<Block[]>([]);
  let loads = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const [received, delivered, blocked] = await Promise.all([sharingClient.inbox(), sharingClient.sent(), sharingClient.blocks()]);
      if (run !== loads) return;
      inbox.value = received;
      sent.value = delivered;
      blocks.value = blocked;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  /** Runs a change. Errors go to the caller, who shows the server's reason. */
  async function change<T>(work: () => Promise<T>): Promise<T> {
    const started = epoch;
    const result = await work();
    if (started === epoch && status.value !== "idle") await load();
    return result;
  }

  const create = (share: NewShare) => change(() => sharingClient.create(share));
  const accept = (id: string, landing?: Landing) => change(() => sharingClient.accept(id, landing));
  const decline = (id: string) => change(() => sharingClient.decline(id));
  const revoke = (id: string) => change(() => sharingClient.revoke(id));
  const block = (username: string) => change(() => sharingClient.block(username));
  const unblock = (uid: string) => change(() => sharingClient.unblock(uid));

  function forget(): void {
    epoch++;
    loads++;
    status.value = "idle";
    error.value = "";
    inbox.value = [];
    sent.value = [];
    blocks.value = [];
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, inbox, sent, blocks, load, create, accept, decline, revoke, block, unblock, forget };
});
