import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { ApiError } from "../../../api/http";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";
import { proposalsClient, type Landing, type Proposal } from "../api/ProposalsClient";

export function isDecidedProposalError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409 && err.message === "That suggestion is already decided.";
}

/** The suggestions agents made that wait for the person's answer, as the server holds them. The text is not kept
 * here (the dialog asks for it). Everything is private: `forget()` and a change of account drop it, and a reply that
 * arrives after that, or after a newer load, is ignored. Changes show only after the server answered. */
export const useProposalsStore = defineStore("proposals", () => {
  const auth = useAuthStore();
  const status = ref<"idle" | "loading" | "ready" | "error">("idle");
  const error = ref("");
  const items = ref<Proposal[]>([]);
  let loads = 0;
  let epoch = 0; // raised by forget(): a change that started before it must not write after it

  async function load(): Promise<void> {
    if (!auth.account) return;
    const run = ++loads;
    if (status.value !== "ready") status.value = "loading";
    try {
      const waiting = await proposalsClient.list();
      if (run !== loads) return;
      items.value = waiting;
      status.value = "ready";
      error.value = "";
    } catch (err) {
      if (run !== loads) return;
      error.value = errorMessage(err);
      status.value = status.value === "ready" ? "ready" : "error";
    }
  }

  /** Runs a change. Errors go to the caller, who shows the server's reason. */
  async function change<T>(id: string, work: () => Promise<T>): Promise<T> {
    const started = epoch;
    async function refresh(): Promise<void> {
      if (started !== epoch || status.value === "idle") return;
      items.value = items.value.filter((item) => item.id !== id);
      await load();
    }
    try {
      const result = await work();
      await refresh();
      return result;
    } catch (err) {
      if (isDecidedProposalError(err)) await refresh();
      throw err;
    }
  }

  const accept = (id: string, landing?: Landing) => change(id, () => proposalsClient.accept(id, landing));
  const decline = (id: string) => change(id, () => proposalsClient.decline(id));

  function forget(): void {
    epoch++;
    loads++;
    status.value = "idle";
    error.value = "";
    items.value = [];
  }

  watch(() => auth.account?.id, forget, { flush: "sync" });

  return { status, error, items, load, accept, decline, forget };
});
