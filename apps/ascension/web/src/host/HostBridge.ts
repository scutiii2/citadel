export type ConnectResult = "ready" | "no-ticket" | "failed";
export interface HostBridgeOptions {
  fetchFn: typeof fetch;
  hostOrigin: string;
  win: Window;
  parentWin: Window | null;
}

/** One launch ticket becomes one in-memory session; no storage or cookie access. */
export class HostBridge {
  private token = "";
  private ended = false;
  private connection: Promise<ConnectResult> | null = null;
  private readonly options: HostBridgeOptions;

  constructor(options: HostBridgeOptions) {
    const origin = new URL(options.hostOrigin);
    if (!["http:", "https:"].includes(origin.protocol) || origin.origin !== options.hostOrigin) {
      throw new Error("The Ember host must be an HTTP(S) origin");
    }
    this.options = options;
  }

  connect(): Promise<ConnectResult> {
    return this.connection ??= this.redeem();
  }

  private async redeem(): Promise<ConnectResult> {
    const { win, fetchFn } = this.options;
    const ticket = new URLSearchParams(win.location.hash.slice(1)).get("ticket");
    if (win.location.hash) win.history.replaceState(null, "", win.location.pathname + win.location.search);
    if (!ticket) return "no-ticket";
    try {
      const response = await fetchFn("/session/redeem", {
        method: "POST", credentials: "omit", redirect: "error",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket }),
      });
      if (!response.ok) return "failed";
      const data: unknown = await response.json();
      if (!data || typeof data !== "object" || !("token" in data) || typeof data.token !== "string" || !data.token.trim()) return "failed";
      if (this.ended) return "failed";
      this.token = data.token;
      return "ready";
    } catch { return "failed"; }
  }

  authHeader(): Record<string, string> { return this.token ? { Authorization: `Bearer ${this.token}` } : {}; }
  endSession(): void { this.ended = true; this.token = ""; }
  notifyReady(): void { this.post({ source: "game", type: "ready" }); }
  notifyResize(height: number): void {
    if (Number.isFinite(height) && height > 0) this.post({ source: "game", type: "resize", height: Math.ceil(height) });
  }
  requestClose(): void { this.post({ source: "game", type: "close" }); }
  /** The only incoming command is a host close; origin and source must both match. */
  listen(onClose: () => void): () => void {
    const { win, parentWin, hostOrigin } = this.options;
    const listener = (event: MessageEvent): void => {
      if (event.origin !== hostOrigin || event.source !== parentWin || !parentWin || parentWin === win) return;
      const data: unknown = event.data;
      if (data && typeof data === "object" && "source" in data && data.source === "host" && "type" in data && data.type === "close") onClose();
    };
    win.addEventListener("message", listener);
    return () => win.removeEventListener("message", listener);
  }
  private post(message: Record<string, unknown>): void {
    const { parentWin, win, hostOrigin } = this.options;
    if (parentWin && parentWin !== win) parentWin.postMessage(message, hostOrigin);
  }
}
