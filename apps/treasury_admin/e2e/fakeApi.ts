import type { Page, Route } from "@playwright/test";

/** A stand-in for portcullis: answers the calls Treasury Admin makes, so the built app runs in a real browser
 * without portcullis or Treasury. Any call not listed is recorded in `unexpected`, and the test fails on it. */
export const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: ["Administrator"],
  permissions: ["settings.manage"],
};

export const CONNECTIONS = {
  connections: [
    { name: "data", spec: { type: "sqlite", path: "ember.db" }, source: "built-in", used_by: ["ember"] },
    { name: "reports", spec: { type: "postgres", dsn: "${REPORTS_DSN}" }, source: "saved", used_by: ["legion"] },
  ],
  default_cache: { ttl_seconds: 30, max_entries: 1000, negative_ttl_seconds: 5 },
  default_cache_stored: false,
};

export interface FakeState { unexpected: string[]; }
export const newState = (): FakeState => ({ unexpected: [] });

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export async function installFakeApi(page: Page, state: FakeState): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    if (method === "GET" && pathname === "/api/auth/me") return json(route, ACCOUNT);
    if (method === "GET" && pathname === "/api/admin/treasury") return json(route, { reachable: true, instances: [{ name: "stronghold", connections: ["data"] }, { name: "armory", connections: [] }], portcullis: { instance: "stronghold", connection: "data" } });
    if (method === "GET" && pathname === "/api/admin/treasury/connections") return json(route, CONNECTIONS);
    if (method === "GET" && pathname === "/api/admin/treasury/services") return json(route, { services: [{ name: "armory", url: "http://armory:29600", source: "registered", registered: "http://armory:29600", pinned: null }, { name: "legion", url: "http://legion:29603", source: "pinned", registered: null, pinned: "http://legion:29603" }] });
    if (method === "GET" && pathname === "/api/admin/treasury/outside") return json(route, { groups: [{ service_id: "a".repeat(32), name: "bard", used_by: ["legion"], origins: [{ origin_id: "b".repeat(32), origin: "http://bard:29400" }] }] });
    state.unexpected.push(`${method} ${pathname}`);
    return json(route, { detail: "unexpected request" }, 500);
  });
}
