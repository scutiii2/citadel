/**
 * Where the API lives and how the app proves who it is.
 *
 * Browser build: same origin, session cookie (base is "", no token).
 * Windows app (Tauri): the page is served from its own origin, so the cookie
 * (SameSite=Strict) cannot be used. The user enters the Portcullis URL once;
 * the login answer carries a session token that is sent as a bearer.
 */

const URL_KEY = "ember.server_url";
const TOKEN_KEY = "ember.session_token";

/** True inside the Tauri webview. */
export function isDesktop(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function read(key: string): string {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}

function write(key: string, value: string): void {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch { /* storage blocked: the setting lasts until the page closes */ }
}

/** "http://host:port" without a trailing slash, or null if `value` is not an http(s) URL. */
export function normalizeServerUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.origin;
  } catch { return null; }
}

/** The configured Portcullis origin. Always "" in the browser build. */
export function serverBase(): string {
  return isDesktop() ? read(URL_KEY) : "";
}

export function setServerBase(value: string): boolean {
  const origin = normalizeServerUrl(value);
  if (!origin) return false;
  write(URL_KEY, origin);
  return true;
}

/** True once the app can reach a server: always in the browser, after setup in the Windows app. */
export function hasServer(): boolean {
  return !isDesktop() || serverBase() !== "";
}

/** `/api/...` becomes an absolute URL in the Windows app, stays relative in the browser. */
export function apiUrl(path: string): string {
  return serverBase() + path;
}

export function sessionToken(): string {
  return isDesktop() ? read(TOKEN_KEY) : "";
}

export function setSessionToken(token: string): void {
  if (isDesktop()) write(TOKEN_KEY, token);
}

/** Headers every API call carries: the bearer in the Windows app, nothing in the browser. */
export function authHeaders(): Record<string, string> {
  const token = sessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** `fetch` credentials: the browser sends its cookie; the Windows app sends none (it is cross-origin). */
export function credentialsMode(): RequestCredentials {
  return isDesktop() ? "omit" : "same-origin";
}

/** Origin for links the user copies (share links): the server in the Windows app, this page in the browser. */
export function publicOrigin(): string {
  return isDesktop() ? serverBase() : window.location.origin;
}

/**
 * An `<img>`/`<audio>` cannot send a bearer header, so the Windows app fetches the file and hands the element
 * a blob: URL. The browser build uses the plain URL (cookie). Callers revoke blob URLs they are done with.
 */
export async function mediaUrl(path: string): Promise<string> {
  if (!isDesktop()) return path;
  const response = await fetch(apiUrl(path), { credentials: "omit", headers: authHeaders() });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return URL.createObjectURL(await response.blob());
}
