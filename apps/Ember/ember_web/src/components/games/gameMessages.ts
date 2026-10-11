export type GameMessage = { type: "ready" | "close" } | { type: "resize"; height: number };
export class GameMessages {
  private readonly registeredUrl: string;
  private readonly source: () => Window | null;
  constructor(registeredUrl: string, source: () => Window | null) { this.registeredUrl = registeredUrl; this.source = source; }
  private origin(url: string): string | null {
    try { const parsed = new URL(url); return ["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password ? parsed.origin : null; } catch { return null; }
  }
  allows(url: string): boolean { const origin = this.origin(this.registeredUrl); return origin !== null && origin === this.origin(url); }
  receive(event: MessageEvent): GameMessage | null {
    const source = this.source();
    if (!source || event.source !== source || event.origin !== this.origin(this.registeredUrl)) return null;
    const data: unknown = event.data;
    if (!data || typeof data !== "object" || !("source" in data) || data.source !== "game" || !("type" in data)) return null;
    if (data.type === "ready" || data.type === "close") return { type: data.type };
    if (data.type === "resize" && "height" in data && typeof data.height === "number" && Number.isFinite(data.height)) return { type: "resize", height: Math.min(4000, Math.max(320, Math.ceil(data.height))) };
    return null;
  }
}
