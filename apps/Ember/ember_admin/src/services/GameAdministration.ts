import { reactive } from "vue";
import { GamesAdminClient, type RegistryGame } from "../api/GamesAdminClient";
import { errorMessage } from "../utils/errors";
export class GameAdministration {
  readonly state = reactive({ games: [] as RegistryGame[], url: "", loading: false, busy: false, error: "", notice: "", removing: null as RegistryGame | null });
  private readonly client: GamesAdminClient;
  private revision = 0;
  private loadSequence = 0;
  constructor(client: GamesAdminClient) { this.client = client; }
  dispose(): void { this.revision++; }
  async load(): Promise<void> {
    const revision = this.revision; const sequence = ++this.loadSequence; this.state.loading = true;
    const current = () => revision === this.revision && sequence === this.loadSequence;
    try { const games = await this.client.registry(); if (current()) this.state.games = games; }
    catch (error) { if (current()) this.state.error = errorMessage(error); }
    finally { if (current()) this.state.loading = false; }
  }
  private async mutate(action: () => Promise<string>): Promise<void> {
    if (this.state.busy) return;
    const revision = this.revision; this.state.busy = true; this.state.error = ""; this.state.notice = "";
    try { const notice = await action(); if (revision !== this.revision) return; this.state.notice = notice; await this.load(); }
    catch (error) { if (revision === this.revision) this.state.error = errorMessage(error); }
    finally { if (revision === this.revision) this.state.busy = false; }
  }
  register(): Promise<void> { return this.mutate(async () => { const game = await this.client.register(this.state.url.trim()); this.state.url = ""; return `Registered ${game.name}`; }); }
  refresh(game: RegistryGame): Promise<void> { return this.mutate(async () => { await this.client.refresh(game.id); return `Refreshed ${game.name}`; }); }
  askDeregister(game: RegistryGame): void { this.state.removing = game; this.state.error = ""; }
  cancelDeregister(): void { if (!this.state.busy) this.state.removing = null; }
  deregister(): Promise<void> {
    const game = this.state.removing; if (!game) return Promise.resolve();
    return this.mutate(async () => { await this.client.deregister(game.id); this.state.removing = null; return `Deregistered ${game.name}`; });
  }
}
