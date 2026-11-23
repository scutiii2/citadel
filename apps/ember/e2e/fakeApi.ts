import type { Page, Route } from "@playwright/test";

/** A stand-in for portcullis: answers the calls Ember makes, so the built app runs in a real browser
 * without a server. Any call not listed is recorded in `unexpected`, and the test fails on it. */
export const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: ["User"],
  permissions: ["chat.use", "tools.view", "tools.execute", "tickets.create", "extensions.personal.manage"],
};

const CAPABILITIES = [
  { name: "gen", enabled: true, label: "Generator", tools: ["password"], resources: [], has_gui: true },
  { name: "notes", enabled: true, label: "Notes", tools: ["read"], resources: [] },
];

const AGENTS = [
  { id: "ember", label: "EMBER", entry: true, orchestrator: false, focus: "Talks with you.", status: "running", provider: null, gateway: null, model: null, tiers: [] },
];

const USAGE_REPORT = {
  total_cost: null, currency: "USD", unpriced_tokens: 0, days: 7, since: "2026-11-16", total_tokens: 1200,
  input_tokens: 800, output_tokens: 400, summary_tokens: 0, turns: 4, chats: 2, by_agent: [], daily: [], hourly: Array(24).fill(0),
  group_by: "agent", groups: [],
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
    if (method === "GET") {
      const table: Record<string, unknown> = {
        "/api/auth/me": ACCOUNT,
        "/api/capabilities": CAPABILITIES,
        "/api/agents": AGENTS,
        "/api/account-agents": { disabled: [] },
        "/api/tickets/unread-count": { count: 1 },
        "/api/tickets": [],
        "/api/account/devices": [],
        "/api/account/tuning": { limits: { max_output_tokens: null, max_tool_rounds: null }, ceiling: null },
        "/api/chats": [],
        "/api/nav-preferences": { order: [], pinned: [], hidden: [] },
        "/api/settings": { force_tool_approval: false },
        "/api/settings/pages": { hidden: [] },
        "/api/usage/records": [],
        "/api/user-extensions": [],
        "/api/usage": { six_hour: { used: 10, limit: 0 }, weekly: { used: 100, limit: 0 }, report: USAGE_REPORT },
      };
      if (pathname in table) return json(route, table[pathname]);
    }
    // Tool discovery speaks MCP; the pages cope with it being unavailable.
    if (method === "POST" && pathname === "/api/mcp/server") return json(route, { detail: "not available in the test" }, 503);
    state.unexpected.push(`${method} ${pathname}`);
    return json(route, { detail: "unexpected request" }, 500);
  });
}
