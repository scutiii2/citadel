import { apiUrl, authHeaders, credentialsMode, hasServer, isDesktop, reportServerLost } from "../utils/server";

/** JSON calls to Portcullis's REST routes: same origin with the session cookie in the browser, the configured server with a bearer token in the Windows app. */

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** True when `err` is an ApiError with one of `statuses`. */
export function isApiStatus(err: unknown, ...statuses: number[]): boolean {
  return err instanceof ApiError && statuses.includes(err.status);
}

/** 401: no session, or it expired. */
export class UnauthorizedError extends ApiError {}

let unauthorizedHandler: (() => void) | null = null;

/** Called on every 401 (the auth store uses it to drop the account). */
export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler;
}

/** For requests made outside apiRequest (the turn event stream). */
export function reportUnauthorized(): void {
  unauthorizedHandler?.();
}

/** FastAPI errors: `detail` is a string, or a list of field errors (422). */
function messageOf(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (d as { msg?: unknown } | null)?.msg)
      .filter((m): m is string => typeof m === "string");
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export async function apiRequest<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
  signal?: AbortSignal,
): Promise<T> {
  // Every POST is JSON, even with no payload: ember_api rejects anything
  // else as a CSRF guard. Other methods send a body only when given one.
  // `headers` adds request headers such as an Idempotency-Key.
  // Windows app before its server is set: same as logged out, so the router shows the login page with the server field.
  if (!hasServer()) throw new UnauthorizedError(401, "Set the server address first");
  const init: RequestInit = { method, credentials: credentialsMode() };
  if (signal) init.signal = signal;
  const sent: Record<string, string> = { ...authHeaders(), ...headers };
  if (method === "POST" || body !== undefined) {
    sent["Content-Type"] = "application/json";
    init.body = JSON.stringify(body ?? {});
  }
  if (Object.keys(sent).length > 0) init.headers = sent;
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch (err) {
    // Windows app: a network failure means the server is gone, so go back to the connect screen. Aborts pass through.
    if (isDesktop() && err instanceof TypeError) {
      reportServerLost();
      throw new ApiError(0, "Cannot reach the server. Check your network and the server address.");
    }
    throw err;
  }
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = messageOf(data, response.statusText || `HTTP ${response.status}`);
    if (response.status === 401) {
      unauthorizedHandler?.();
      throw new UnauthorizedError(401, message);
    }
    const code = (data as { error?: { code?: unknown } } | null)?.error?.code;
    throw new ApiError(response.status, message, typeof code === "string" ? code : undefined);
  }
  return data as T;
}
