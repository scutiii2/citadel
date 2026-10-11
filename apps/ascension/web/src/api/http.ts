import type { HostBridge } from "../host/HostBridge";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}
export class UnauthorizedError extends ApiError {}
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export class HttpClient {
  private readonly fetchFn: typeof fetch;
  private readonly bridge: HostBridge;
  private readonly onEnded: () => void;
  constructor(fetchFn: typeof fetch, bridge: HostBridge, onEnded: () => void) {
    this.fetchFn = fetchFn; this.bridge = bridge; this.onEnded = onEnded;
  }
  async request<T>(method: HttpMethod, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
    const sent = { ...headers, ...this.bridge.authHeader() };
    const init: RequestInit = { method, credentials: "omit", redirect: "error", headers: sent };
    if (method === "POST" || body !== undefined) {
      sent["Content-Type"] = "application/json";
      init.body = JSON.stringify(body ?? {});
    }
    const response = await this.fetchFn(path, init);
    if (response.status === 204) return undefined as T;
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const message = this.messageOf(data, response.statusText || `HTTP ${response.status}`);
      if (response.status === 401) {
        this.bridge.endSession(); this.onEnded();
        throw new UnauthorizedError(401, message);
      }
      throw new ApiError(response.status, message);
    }
    return data as T;
  }
  private messageOf(data: unknown, fallback: string): string {
    if (!data || typeof data !== "object") return fallback;
    const fields = data as { error?: unknown; detail?: unknown };
    if (typeof fields.error === "string") return fields.error;
    if (typeof fields.detail === "string") return fields.detail;
    if (Array.isArray(fields.detail)) {
      const messages = fields.detail.map(d => (d as { msg?: unknown } | null)?.msg).filter((m): m is string => typeof m === "string");
      if (messages.length) return messages.join("; ");
    }
    return fallback;
  }
}
