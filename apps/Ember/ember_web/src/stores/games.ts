import { defineStore } from "pinia";
import { reactive, toRefs, watch } from "vue";
import { GamesClient, type GameInfo } from "../api/GamesClient";
import { errorMessage } from "../utils/errors";
import { useAuthStore } from "./auth";

class GamesController {
  readonly state = reactive({ games: [] as GameInfo[], activeId: null as string | null, launchUrl: "", error: "", loading: false, launching: false, loaded: false });
  private readonly client: GamesClient;
  private readonly account: () => number | null;
  private epoch = 0;
  private launchSequence = 0;
  private listSequence = 0;
  private pendingList: Promise<void> | null = null;
  constructor(client: GamesClient, account: () => number | null) { this.client = client; this.account = account; }
  reset(): void { this.epoch++; this.pendingList = null; this.close(); Object.assign(this.state, { games: [], error: "", loaded: false, loading: false }); }
  close(): void { this.launchSequence++; this.state.activeId = null; this.state.launchUrl = ""; this.state.launching = false; }
  load(): Promise<void> { this.pendingList = this.fetchList(); return this.pendingList; }
  private async fetchList(): Promise<void> {
    const owner = this.account(); if (owner === null) return;
    const epoch = this.epoch; const sequence = ++this.listSequence;
    this.state.loading = true; this.state.error = "";
    const current = () => epoch === this.epoch && sequence === this.listSequence && owner === this.account();
    try { const games = await this.client.list(); if (current()) { this.state.games = games; this.state.loaded = true; } }
    catch (error) { if (current()) this.state.error = errorMessage(error); }
    finally { if (current()) this.state.loading = false; }
  }
  async ensureLoaded(): Promise<void> { if (!this.state.loaded) await (this.state.loading && this.pendingList ? this.pendingList : this.load()); }
  async open(id: string): Promise<void> {
    this.close(); const owner = this.account(); if (owner === null) return;
    const epoch = this.epoch; const sequence = this.launchSequence;
    this.state.launching = true; this.state.error = "";
    const current = () => epoch === this.epoch && sequence === this.launchSequence && owner === this.account();
    try { const launch = await this.client.launch(id); if (current()) { this.state.activeId = id; this.state.launchUrl = launch.url; } }
    catch (error) { if (current()) this.state.error = errorMessage(error); }
    finally { if (current()) this.state.launching = false; }
  }
}
export const useGamesStore = defineStore("games", () => {
  const auth = useAuthStore();
  const controller = new GamesController(new GamesClient(), () => auth.account?.id ?? null);
  watch(() => auth.account?.id ?? null, () => controller.reset());
  return { ...toRefs(controller.state), load: controller.load.bind(controller), ensureLoaded: controller.ensureLoaded.bind(controller), open: controller.open.bind(controller), close: controller.close.bind(controller), reset: controller.reset.bind(controller) };
});
