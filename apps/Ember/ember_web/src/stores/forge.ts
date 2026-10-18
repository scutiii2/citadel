import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import {
  forgeClient,
  type ForgeCreatedWorker,
  type ForgeGroup,
  type ForgeGroupPatch,
  type ForgePlans,
  type ForgeProvider,
  type ForgeWorker,
} from "../api/ForgeClient";
import { watchGroup } from "../services/forgeStream";
import { errorMessage } from "../utils/errors";
import { applyEvent, emptyTranscript, type TranscriptState } from "../utils/forgeTranscript";
import { useAuthStore } from "./auth";

type CreateMode = Parameters<typeof forgeClient.createGroup>[1];

/** The account's Forge workers and groups, and the live transcript of the open group.
 * Loaded on first use and dropped when the user changes. Actions that change something throw
 * ember_api's message so the dialog that called them can show it. */
export const useForgeStore = defineStore("forge", () => {
  const auth = useAuthStore();

  const workers = ref<ForgeWorker[]>([]);
  const plans = ref<ForgePlans>({ claude: [], codex: [] });
  const groups = ref<ForgeGroup[]>([]);
  const selectedId = ref<number | null>(null);
  const transcript = ref<TranscriptState>(emptyTranscript());
  const connection = ref<"idle" | "live" | "lost">("idle");
  const loading = ref(false);
  const loadError = ref("");
  let loaded = false;
  let controller: AbortController | null = null;
  // Bumped on every account change: answers and events for the previous account are ignored.
  let generation = 0;

  const allowed = computed(() => auth.hasPermission("forge.use"));
  const selected = computed(() => groups.value.find((g) => g.id === selectedId.value) ?? null);

  watch(
    () => (allowed.value ? (auth.account?.id ?? null) : null),
    () => {
      generation += 1;
      controller?.abort();
      controller = null;
      workers.value = [];
      groups.value = [];
      plans.value = { claude: [], codex: [] };
      selectedId.value = null;
      transcript.value = emptyTranscript();
      connection.value = "idle";
      loading.value = false;
      loadError.value = "";
      loaded = false;
    },
  );

  async function refresh(): Promise<void> {
    if (!allowed.value) return;
    const started = generation;
    if (!loaded) loading.value = true;
    try {
      const [nextWorkers, nextGroups, nextPlans] = await Promise.all([
        forgeClient.workers(),
        forgeClient.groups(),
        forgeClient.plans(),
      ]);
      if (started !== generation) return;
      workers.value = nextWorkers;
      groups.value = nextGroups;
      plans.value = nextPlans;
      loadError.value = "";
      loaded = true;
      if (selectedId.value !== null && !nextGroups.some((g) => g.id === selectedId.value)) select(null);
    } catch (err) {
      if (started === generation) loadError.value = errorMessage(err);
    } finally {
      if (started === generation) loading.value = false;
    }
  }

  async function ensureLoaded(): Promise<void> {
    if (!loaded) await refresh();
  }

  function startWatch(id: number, after: number): void {
    const mine = new AbortController();
    controller = mine;
    const started = generation;
    connection.value = "live";
    watchGroup(
      id,
      after,
      (event) => {
        if (!mine.signal.aborted && started === generation) transcript.value = applyEvent(transcript.value, event);
      },
      mine.signal,
    )
      .then(async (end) => {
        if (end === "gone" && !mine.signal.aborted) await refresh();
      })
      .catch(() => {
        if (!mine.signal.aborted && started === generation) connection.value = "lost";
      });
  }

  function select(id: number | null): void {
    controller?.abort();
    controller = null;
    selectedId.value = id;
    transcript.value = emptyTranscript();
    connection.value = "idle";
    if (id !== null) startWatch(id, 0);
  }

  /** Watches the open group again, from the newest message already shown. */
  function reconnect(): void {
    const id = selectedId.value;
    if (id === null) return;
    controller?.abort();
    startWatch(id, transcript.value.cursor);
  }

  /** Stops the live watch (the page was left) but remembers which group was open. */
  function leave(): void {
    controller?.abort();
    controller = null;
    connection.value = "idle";
  }

  function upsert(group: ForgeGroup): void {
    const at = groups.value.findIndex((g) => g.id === group.id);
    if (at < 0) groups.value = [group, ...groups.value];
    else groups.value.splice(at, 1, group);
  }

  async function createGroup(title: string, mode: CreateMode): Promise<ForgeGroup> {
    const group = await forgeClient.createGroup(title, mode);
    upsert(group);
    select(group.id);
    return group;
  }

  async function updateGroup(id: number, patch: ForgeGroupPatch): Promise<ForgeGroup> {
    const group = await forgeClient.updateGroup(id, patch);
    upsert(group);
    return group;
  }

  async function removeGroup(id: number): Promise<void> {
    await forgeClient.removeGroup(id);
    groups.value = groups.value.filter((g) => g.id !== id);
    if (selectedId.value === id) select(null);
  }

  async function invite(groupId: number, workerId: number, folder: string): Promise<void> {
    upsert(await forgeClient.invite(groupId, workerId, folder));
  }

  async function removeMember(groupId: number, workerId: number): Promise<void> {
    upsert(await forgeClient.removeMember(groupId, workerId));
  }

  /** The token is returned for the caller to show once; the store keeps only the worker. */
  async function createWorker(provider: ForgeProvider, label: string): Promise<ForgeCreatedWorker> {
    const created = await forgeClient.createWorker(provider, label);
    const { token: _token, ...worker } = created;
    workers.value = [...workers.value, worker];
    return created;
  }

  async function removeWorker(id: number): Promise<void> {
    await forgeClient.removeWorker(id);
    await refresh();
  }

  async function savePlans(provider: ForgeProvider, list: string[]): Promise<void> {
    await forgeClient.setPlans(provider, list);
    await refresh();
  }

  async function send(text: string): Promise<void> {
    if (selectedId.value !== null) await forgeClient.send(selectedId.value, text);
  }

  async function stop(): Promise<void> {
    if (selectedId.value !== null) await forgeClient.stop(selectedId.value);
  }

  async function answer(requestId: string, allow: boolean): Promise<void> {
    if (selectedId.value !== null) await forgeClient.answerPermission(selectedId.value, requestId, allow);
  }

  return {
    workers, plans, groups, selectedId, selected, transcript, connection, loading, loadError,
    ensureLoaded, refresh, select, reconnect, leave,
    createGroup, updateGroup, removeGroup, invite, removeMember,
    createWorker, removeWorker, savePlans, send, stop, answer,
  };
});
