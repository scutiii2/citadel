import type { Page, Route } from "@playwright/test";

/** A stand-in for portcullis: answers the calls Stronghold Admin makes, so the built app runs in a real browser
 * without portcullis or Stronghold. Any call not listed is recorded in `unexpected`, and the test fails on it. */
export const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: ["Administrator"],
  permissions: ["usage.all.view", "logs.view", "traffic.view", "tickets.manage", "settings.manage", "tool_services.manage"],
};

const USAGE = [{ account_id: 1, username: "root", is_active: true, tokens: 1200, turns: 4, last_used_at: null }];

const REPORT = {
  six_hour: { used: 1200, limit: 0, reset_at: null },
  weekly: { used: 1200, limit: 0, reset_at: null },
  report: {
    days: 30, since: "2026-11-01T00:00:00", total_tokens: 1200, input_tokens: 1000, output_tokens: 200, summary_tokens: 0,
    turns: 4, chats: 1, by_agent: [], daily: [], hourly: Array(24).fill(0), group_by: "agent", groups: [],
  },
};

const ALLOWANCES = [{
  account_id: 1, username: "root", auto_use: false,
  resets: [{ id: "r_1", kind: "both", granted_at: "2026-11-20T00:00:00", expires_at: null }],
  boosts: [{ id: "b_1", windows: ["weekly"], percent: 50, granted_at: "2026-11-20T00:00:00", ends_at: "2099-01-01T00:00:00" }],
}];

const ANALYTICS = {
  period: "7d",
  bucket: "day",
  kinds: ["action"],
  totals: { action: { current: 3, previous: 1 } },
  series: [{ bucket: "2026-11-20T00:00:00", counts: { action: 3 } }],
  top_sources: { action: [{ source: "chat", count: 3 }] },
  accounts: { action: [{ account_id: 1, username: "root", count: 3 }] },
  heatmap: [{ weekday: 1, hour: 3, count: 3 }],
};

const USAGE_SETTINGS = {
  usage: { six_hour_token_limit: 0, weekly_token_limit: 0, max_context_tokens_per_chat: 0, auto_summarize_ratio: 0.8, cached_token_weight: 0.1 },
  pricing: { currency: "USD", models: { sonnet: { input: 3, output: 15 } } },
  stored: { usage: false, pricing: true },
};

const BRAIN_SETTINGS = {
  stack: { max_items: 50, max_item_chars: 500, compact_item_chars: 300, warn_ratio: 0.8 },
  long_term: { max_record_chars: 20000, max_files: 500, max_total_bytes: 5000000, search_limit: 10 },
  ranges: {},
  root: "/data/brain",
  stored: { stack: false, long_term: true },
};

const SERVICES = [
  { name: "bard", label: "Bard", enabled: true, service_id: "s", has_token: true, origins: [{ origin_id: "o1", origin: "http://bard:29400", has_override: false }], ready: true, reason: null },
  { name: "scribe", label: "Scribe", enabled: false, service_id: null, has_token: false, origins: [], ready: false, reason: "Scribe is disabled in Stronghold Admin." },
];

export interface FakeState { unexpected: string[]; sent: { call: string; body: unknown }[]; }
export const newState = (): FakeState => ({ unexpected: [], sent: [] });

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

export async function installFakeApi(page: Page, state: FakeState): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    if (method === "GET") {
      if (pathname === "/api/auth/me") return json(route, ACCOUNT);
      if (pathname === "/api/admin/usage") return json(route, USAGE);
      if (pathname === "/api/admin/usage/1") return json(route, REPORT);
      if (pathname === "/api/admin/usage/1/records") return json(route, []);
      if (pathname === "/api/admin/usage-allowances") return json(route, ALLOWANCES);
      if (pathname === "/api/logs/analytics") return json(route, ANALYTICS);
      if (pathname === "/api/admin/tickets/stats") return json(route, { open: 2, urgent: 1, groups: 1 });
      if (pathname === "/api/admin/tickets") return json(route, { tickets: [] });
      if (pathname === "/api/admin/ticket-groups") return json(route, { groups: [] });
      if (pathname === "/api/admin/stronghold-usage-settings") return json(route, USAGE_SETTINGS);
      if (pathname === "/api/admin/stronghold-brain-settings") return json(route, BRAIN_SETTINGS);
      if (pathname === "/api/admin/tool-services") return json(route, { services: SERVICES });
    }
    if (pathname.startsWith("/api/admin/usage-allowances/") && (method === "POST" || method === "DELETE")) {
      state.sent.push({ call: `${method} ${pathname}`, body: request.postDataJSON() });
      return method === "DELETE" ? route.fulfill({ status: 204 }) : json(route, { done: 1, failed: [] });
    }
    state.unexpected.push(`${method} ${pathname}`);
    return json(route, { detail: "unexpected request" }, 500);
  });
}
