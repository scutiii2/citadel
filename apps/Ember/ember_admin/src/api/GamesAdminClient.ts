import { apiRequest } from "./http";
export interface RegistryGame { id: string; name: string; description: string; icon: string; version: string; url: string; enabled: boolean; }
export class GamesAdminClient {
  private readonly request: typeof apiRequest;
  constructor(request: typeof apiRequest = apiRequest) { this.request = request; }
  async registry(): Promise<RegistryGame[]> { return (await this.request<{ games: RegistryGame[] }>("GET", "/api/games/registry")).games; }
  register(url: string): Promise<RegistryGame> { return this.request("POST", "/api/games", { url }); }
  refresh(id: string): Promise<RegistryGame> { return this.request("POST", `/api/games/${encodeURIComponent(id)}/refresh`); }
  deregister(id: string): Promise<void> { return this.request("DELETE", `/api/games/${encodeURIComponent(id)}`); }
}
