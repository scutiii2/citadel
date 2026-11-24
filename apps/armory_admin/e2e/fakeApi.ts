import type { Page, Route } from "@playwright/test";

/** A stand-in for portcullis: answers the calls Armory Admin makes, so the built app runs in a real browser
 * without portcullis or Armory. Any call not listed is recorded in `unexpected`, and the test fails on it. */
export const ACCOUNT = {
  id: 1,
  username: "root",
  email: "root@example.com",
  email_verified: true,
  roles: ["Administrator"],
  permissions: ["capabilities.manage", "tickets.manage", "settings.manage"],
};

const capability = (name: string, over: Record<string, unknown> = {}) =>
  ({ name, label: name, enabled: true, tools: [], resources: [], has_gui: false, load_error: null, missing: false, loaded: true, ...over });

export const CAPABILITIES = [
  capability("pdf_merger", { label: "PDF merger", tools: ["tool_pdf_inspect", "tool_pdf_merge"] }),
  capability("fresh", { label: "Fresh", enabled: false, loaded: false }),
  capability("broken", { label: "Broken", enabled: false, load_error: "RuntimeError: boom" }),
];

const TICKETS = {
  tags: { email: "Mail problems", other: "Anything else" },
  auto_hourly_cap: 5,
  recent_hours: 24,
  elevation: {},
  laya: { min_confidence: 0.7, candidates: 5, timeout_seconds: 20 },
};

const ENVIRONMENT = {
  settings: [
    { field: "stronghold_url", label: "Stronghold address", group: "Services", kind: "url", help: "", secret: false, restart: false, stored: true, value: "http://127.0.0.1:29650" },
    { field: "media_signing_key", label: "Video link signing key", group: "Links", kind: "text", help: "", secret: true, restart: true, stored: false, has_value: false },
    { field: "obsidian_allow_write", label: "Allow writes", group: "Folders", kind: "bool", help: "", secret: false, restart: false, stored: false, value: false },
  ],
};

const lifetimes = { file_ttl_hours: 6, sweep_interval_minutes: 10, download_link_minutes: 60 };
const LIMITS = {
  pdf_merger: { ...lifetimes, mcp_wait_seconds: 100, stored: false, limits: { max_file_mb: 100, max_session_mb: 500, max_segments: 50, max_output_pages: 2000, max_image_megapixels: 80, max_concurrent_merges: 2, job_timeout_seconds: 120 } },
  media_downloader: { ...lifetimes, stored: false, limits: { max_file_mb: 500, max_duration_minutes: 120, max_session_mb: 2048, max_concurrent_downloads: 2, max_queued_downloads: 8, job_timeout_minutes: 30, max_caller_downloads: 2 } },
};

const EMAIL = { configured: true, smtp_server: "smtp.example.com", smtp_port: 587, security: "", from: "a@example.com", to: ["team@example.com"], allowed_recipient_domains: [], has_password: true };

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
      if (pathname === "/api/auth/me") return json(route, ACCOUNT);
      if (pathname === "/api/capabilities") return json(route, CAPABILITIES);
      if (pathname === "/api/commands") return json(route, []);
      if (pathname === "/api/commands/help") return json(route, { capabilities: [{ capability: "/pdf_merger", summary: "Merge and inspect PDF files." }] });
      if (pathname === "/api/admin/ticket-settings") return json(route, TICKETS);
      if (pathname === "/api/armory-environment") return json(route, ENVIRONMENT);
      if (pathname === "/api/armory-tuning") return json(route, LIMITS);
      if (pathname === "/api/armory-email") return json(route, EMAIL);
      if (pathname === "/api/armory-tool-approval") return json(route, { force_tool_approval: false });
    }
    state.unexpected.push(`${method} ${pathname}`);
    return json(route, { detail: "unexpected request" }, 500);
  });
}
