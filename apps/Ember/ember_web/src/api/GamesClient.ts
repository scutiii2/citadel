import { apiRequest } from "./http";
export interface GameInfo { id: string; name: string; description: string; icon: string; wallpaper: string; symbols: string[]; version: string; url: string; }
export class GamesClient {
  private readonly request: typeof apiRequest;
  constructor(request: typeof apiRequest = apiRequest) { this.request = request; }
  async list(): Promise<GameInfo[]> { return (await this.request<{ games: GameInfo[] }>("GET", "/api/games")).games; }
  launch(id: string): Promise<{url: string}> { return this.request("POST", `/api/games/${encodeURIComponent(id)}/launch`); }
}
