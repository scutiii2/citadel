import type { Page, Route } from "@playwright/test";

/** A stand-in for ember_api, answering what the browser asks of it. The real
 * server (and ai_agent behind it) is not needed: the point is to run the built
 * app in a real browser, through login, sending a question and reading the
 * streamed answer. Anything the app asks that is not listed here is recorded in
 * `unexpected`, and the test fails on it, so the fake cannot drift unnoticed. */

export const ACCOUNT = {
  id: 1,
  username: "ada",
  email: "ada@example.com",
  email_verified: true,
  roles: ["Member"],
  permissions: ["chat.use", "chat.share", "files.upload", "extensions.personal.manage"],
};

/** The same person with the Administrator role, for the pages that need `admin.manage`. */
export const ADMIN_ACCOUNT = {
  ...ACCOUNT,
  roles: ["Administrator"],
  permissions: [...ACCOUNT.permissions, "tools.view", "tools.execute", "files.upload", "files.download", "accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage", "settings.manage", "capabilities.manage", "usage.all.view", "extensions.manage"],
};

/** The agent GET /api/agent returns, and the one every new chat is stored with. */
const ENTRY_AGENT = { id: "agent-1", label: "Test Agent" };

/** The agent the main one hands a question to during the turn. */
const DELEGATE = { id: "calc", label: "Calculator", step_id: "d1" };

export const PASSWORD = "correct horse battery";

export interface StoredChat {
  id: string;
  title: string;
  agent_id: string;
  messages: Record<string, unknown>[];
  running: boolean;
  folder_id?: number | null;
  pinned?: boolean;
  save_to_second_brain?: boolean;
}

export interface StoredFolder {
  id: number;
  name: string;
  position: number;
}

export interface StoredNote {
  id: string;
  title: string;
  body: string;
  tags: string[];
  agent_readable: boolean;
  last_editor: "user" | "agent";
  created_at: string;
  updated_at: string;
}

/** What the page sends when it saves a note. */
interface NoteBody {
  title: string;
  body?: string;
  tags?: string[];
  agent_readable?: boolean;
  expected_updated_at?: string;
}

export interface StoredAccount {
  id: number;
  username: string;
  email: string;
  email_verified: boolean;
  is_active: boolean;
  is_protected: boolean;
  created_at: string;
  roles: { id: number; name: string }[];
}

export interface StoredUserExtension {
  id: string;
  label: string;
  description: string;
  url: string;
  header_names: string[];
  enabled: boolean;
  status: "connected" | "error" | "unknown";
  error: string | null;
  tools: string[];
}

export interface StoredCapability {
  name: string;
  enabled: boolean;
  label: string | null;
  /** The tools it offers while it is on; mcp_server lists no tool of a capability that is off. */
  tools: string[];
  resources: string[];
}

export interface StoredRole {
  id: number;
  name: string;
  description: string | null;
  is_protected: boolean;
  permissions: string[];
  account_count: number;
}

export interface StoredTemplate {
  id: number;
  name: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface StoredShare {
  id: number;
  chat_id: string;
  title: string;
  message_count: number;
  created_at: string;
  expires_at: string | null;
}

export interface StoredTicket {
  id: number;
  type: "bug" | "feature" | "other";
  title: string;
  description: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  has_unread?: boolean;
  comments?: { id: number; ticket_id: number; author: string; author_role: "reporter" | "staff" | "ai" | "system"; body: string; created_at: string }[];
}

interface CalendarFeedStub {
  id: string;
  name: string;
  color: string;
  enabled: boolean;
  last_fetch_at: string | null;
  last_error: string | null;
}
interface RuleStub { id: string; channel: string; lead_minutes: number; enabled: boolean }
interface AlertStub { id: string; title: string; start_utc: string; channel: string; created_at: string }

export interface FakeApi {
  calendar: { feeds: CalendarFeedStub[]; rules: RuleStub[]; alerts: AlertStub[] };
  /** Requests captured only by the opt-in native media workspace fake. */
  media: { uploads: { filename: string; data: string }[]; merges: Record<string, unknown>[]; downloads: { url: string; preset: string }[] };
  tickets: Map<number, StoredTicket>;
  /** The agents the account switched off (GET and PUT /api/account-agents). */
  disabledAgents: Set<string>;

  /** The account's private extensions (/api/user-extensions). Header values are never kept or returned. */
  userExtensions: Map<string, StoredUserExtension>;

  /** The capabilities the Capabilities page lists and an administrator can switch (an administrator login only). */
  capabilities: Map<string, StoredCapability>;
  /** The roles the Admin page lists (an administrator login only). */
  roles: Map<number, StoredRole>;
  /** The member's saved prompts. */
  templates: Map<number, StoredTemplate>;
  /** The read-only links of the member's chats. */
  shares: Map<number, StoredShare>;
  /** The member's private notes (/api/notes). */
  notes: Map<string, StoredNote>;
  memories: Map<number, { id: number; text: string; created_at: string }>;
  /** What the Settings tab saves: the administrator's "require approval for every tool". */
  settings: { forceToolApproval: boolean };
  triageStrategy: string | null;
  /** The accounts the Admin page lists (an administrator login only). */
  accounts: Map<number, StoredAccount>;
  /** Requests that no handler knew, as "METHOD /path". */
  unexpected: string[];
  /** The bodies of the questions the page sent, as JSON. */
  turns: Record<string, unknown>[];
  chats: Map<string, StoredChat>;
  folders: Map<number, StoredFolder>;
}

const USAGE = {
  six_hour: { used: 0, limit: 0, reset_at: null },
  weekly: { used: 0, limit: 0, reset_at: null },
  report: {
    days: 30,
    since: "2026-09-03",
    total_tokens: 1500,
    input_tokens: 1200,
    output_tokens: 300,
    total_cost: 0.042,
    currency: "USD",
    unpriced_tokens: 500,
    summary_tokens: 0,
    turns: 1,
    chats: 1,
    group_by: "agent",
    by_agent: [
      { agent: "main", model: "priced-model", tokens: 1000, cost: 0.042 },
      { agent: "helper", model: "unknown-model", tokens: 500, cost: null },
    ],
    groups: [
      { key: "main", tokens: 1000, input_tokens: 800, output_tokens: 200, turns: 1, cost: 0.042 },
      { key: "helper", tokens: 500, input_tokens: 400, output_tokens: 100, turns: 1, cost: null },
    ],
    daily: [],
    hourly: Array.from({ length: 24 }, () => 0),
  },
};

const ADMIN_ACCOUNTS: StoredAccount[] = [
  { id: 1, username: "ada", email: "ada@example.com", email_verified: true, is_active: true, is_protected: true, created_at: "2026-09-01T10:00:00", roles: [{ id: 1, name: "Administrator" }] },
  { id: 2, username: "maria", email: "maria@example.com", email_verified: true, is_active: true, is_protected: false, created_at: "2026-09-12T10:00:00", roles: [{ id: 2, name: "Member" }] },
  { id: 3, username: "joe", email: "joe@example.com", email_verified: false, is_active: true, is_protected: false, created_at: "2026-09-20T10:00:00", roles: [] },
];
const ADMIN_ROLES = [
  { id: 1, name: "Administrator", description: "Everything", is_protected: true, permissions: [...ACCOUNT.permissions, "tools.view", "tools.execute", "files.upload", "files.download", "accounts.view", "accounts.manage", "accounts.delete", "roles.view", "roles.manage", "roles.assign", "invites.manage", "settings.manage", "capabilities.manage", "usage.all.view"], account_count: 1 },
  { id: 2, name: "Member", description: "Default role", is_protected: false, permissions: ["chat.use", "chat.share", "files.upload", "extensions.personal.manage"], account_count: 1 },
  { id: 3, name: "Ops", description: null, is_protected: false, permissions: [], account_count: 0 },
];
const ADMIN_CAPABILITIES: StoredCapability[] = [
  { name: "pdf", enabled: true, label: "PDF files", tools: ["pdf_merge"], resources: [] },
  { name: "legacy", enabled: true, label: "Legacy", tools: ["legacy_tool"], resources: [] },
];
const ADMIN_PERMISSIONS = [
  { name: "chat.use", description: "Chat with the agent" },
  { name: "tools.view", description: "Run mcp_server tools" },
  { name: "roles.manage", description: "Manage accounts" },
  { name: "extensions.manage", description: "Add and remove mcp_server extensions (other MCP servers offered to every client)" },
];

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

const summary = (chat: StoredChat) => ({
  id: chat.id,
  title: chat.title,
  agent_id: chat.agent_id,
  message_count: chat.messages.length,
  created_at: "2026-10-03T09:00:00",
  updated_at: "2026-10-03T09:00:00",
  running: chat.running,
  folder_id: chat.folder_id ?? null,
  pinned: chat.pinned ?? false,
  save_to_second_brain: chat.save_to_second_brain ?? false,
});

const event = (sequence: number, body: Record<string, unknown>) =>
  `id: ${sequence}\ndata: ${JSON.stringify({ sequence, ...body })}\n\n`;

/** What the fake agent answers, in the pieces ember_api would stream it. */
export const ANSWER_PIECES = ["The capital ", "of France ", "is Paris."];
export const ANSWER = ANSWER_PIECES.join("");

export async function installFakeApi(page: Page, options: { admin?: boolean; tickets?: boolean; media?: boolean; calendar?: boolean } = {}): Promise<FakeApi> {
  const api: FakeApi = {
    calendar: { feeds: [], rules: [{ id: "r1", channel: "inapp", lead_minutes: 15, enabled: true }], alerts: [] },
    media: { uploads: [], merges: [], downloads: [] },
    tickets: new Map(),
    disabledAgents: new Set(),
    userExtensions: new Map(),
    settings: { forceToolApproval: false },
    triageStrategy: null,
    accounts: new Map(),
    capabilities: new Map(),
    roles: new Map(),
    templates: new Map(),
    shares: new Map(),
    notes: new Map(),
    memories: new Map(),
    unexpected: [],
    turns: [],
    chats: new Map(),
    folders: new Map(),
  };
  const baseAccount = options.admin ? ADMIN_ACCOUNT : ACCOUNT;
  const account = { ...baseAccount, permissions: [...baseAccount.permissions, ...(options.tickets ? ["tickets.create"] : []), ...(options.calendar ? ["calendar.use"] : []), ...(options.media ? ["tools.view", "tools.execute", "files.download"] : [])] };
  if (options.admin) {
    for (const a of ADMIN_ACCOUNTS) api.accounts.set(a.id, { ...a });
    for (const r of ADMIN_ROLES) api.roles.set(r.id, { ...r });
    for (const c of ADMIN_CAPABILITIES) api.capabilities.set(c.name, { ...c });
  }
  if (options.media) {
    for (const name of ['pdf', 'media']) {
      api.capabilities.set(name, { name, enabled: true, label: name === 'pdf' ? 'PDF merger' : 'Media downloader', tools: [], resources: [] });
    }
  }
  const pdfs = new Map<string, { info: { file_id: string; name: string; kind: string; pages: number; size: number; expires_at: number }; bytes: Buffer }>();
  let videoDone = false;
  let videoPolls = 0;
  const videoBytes = Buffer.from('Mock video download fixture');
  const videoFile = { file_id: 'video-file', name: 'Coastal walk.mp4', kind: 'video', mime: 'video/mp4', size: videoBytes.length, duration: 125, expires_at: Date.now() / 1000 + 21600, download_url: '/api/media-downloader/files/video-file/download' };
  let responseLimits = { max_output_tokens: null as number | null, max_tool_rounds: null as number | null };
  let loggedIn = false;

  // Opt-in media fixtures share routing across this test's browser context.
  await (options.media ? page.context() : page).route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const attachmentContent = path.match(/^\/api\/attachments\/files\/([A-Za-z0-9_-]+)\/content$/);
    if (attachmentContent && request.method() === 'GET') {
      const found = pdfs.get(attachmentContent[1]!);
      if (!found) return json(route, { detail: 'Image expired or unavailable' }, 404);
      return route.fulfill({ status: 200, contentType: found.info.kind === 'image' ? 'image/png' : 'application/pdf', body: found.bytes });
    }
    if (options.media && path.startsWith('/api/pdf-merger/')) {
      const method = request.method();
      if (path === '/api/pdf-merger/files' && method === 'GET') return json(route, [...pdfs.values()].map(f => f.info));
      if (path === '/api/pdf-merger/files' && method === 'POST') {
        const body = request.postDataJSON() as { filename: string; data: string };
        api.media.uploads.push(body);
        const bytes = Buffer.from(body.data, 'base64');
        if (!bytes.toString('ascii', 0, 5).startsWith('%PDF-')) return json(route, { detail: 'Invalid PDF' }, 400);
        const file_id = `pdf-${pdfs.size + 1}`;
        const info = { file_id, name: body.filename, kind: 'pdf', pages: 1, size: bytes.length, expires_at: Date.now() / 1000 + 21600 };
        pdfs.set(file_id, { info, bytes });
        return json(route, info, 201);
      }
      const match = path.match(/^\/api\/pdf-merger\/files\/([^/]+)(?:\/(content|download))?$/);
      if (match) {
        const found = pdfs.get(match[1]!);
        if (!found) return json(route, { detail: 'File not found' }, 404);
        if (method === 'DELETE') { pdfs.delete(match[1]!); return route.fulfill({ status: 204 }); }
        if (method === 'GET') return route.fulfill({ status: 200, contentType: 'application/pdf', headers: match[2] === 'download' ? { 'Content-Disposition': `attachment; filename="${found.info.name}"` } : {}, body: found.bytes });
      }
      if (path === '/api/pdf-merger/merge' && method === 'POST') {
        api.media.merges.push(request.postDataJSON() as Record<string, unknown>);
        return json(route, { job_id: 'pdf-job' }, 202);
      }
      if (path === '/api/pdf-merger/jobs/pdf-job' && method === 'GET') {
        const bytes = samplePdf('Merged document', 2);
        const info = { file_id: 'pdf-output', name: 'merged.pdf', kind: 'pdf', pages: 2, size: bytes.length, expires_at: Date.now() / 1000 + 21600 };
        pdfs.set(info.file_id, { info, bytes });
        return json(route, { job_id: 'pdf-job', state: 'done', done: 2, total: 2, result: { ...info, download_url: '/api/pdf-merger/files/pdf-output/download' }, error: null });
      }
      if (path.endsWith('/cancel') && method === 'POST') return json(route, {});
    }
    if (options.media && path.startsWith('/api/media-downloader/')) {
      const method = request.method();
      if (path === '/api/media-downloader/packages' && method === 'GET') return json(route, []);
      if (path === '/api/media-downloader/probe' && method === 'POST') return json(route, {
        url: (request.postDataJSON() as { url: string }).url, title: 'Coastal walk at sunset', duration: 125, thumbnail: 'https://example.com/thumbnail.jpg', uploader: 'Field recordings',
        options: [
          { id: 'best', label: 'Best quality', kind: 'video', estimated_bytes: 900000000, blocked: true, code: 'too_large', reason: 'Exceeds the file size limit' },
          { id: '720p', label: '720p', kind: 'video', estimated_bytes: 24000000, blocked: false, code: null, reason: null },
          { id: 'audio-mp3', label: 'Audio (MP3)', kind: 'audio', estimated_bytes: 3000000, blocked: false, code: null, reason: null },
        ],
      });
      if (path === '/api/media-downloader/downloads' && method === 'POST') {
        api.media.downloads.push(request.postDataJSON() as { url: string; preset: string });
        return json(route, { job_id: 'video-job' }, 202);
      }
      if (path === '/api/media-downloader/jobs/video-job' && method === 'GET') {
        videoDone = ++videoPolls > 1;
        return json(route, { job_id: 'video-job', state: videoDone ? 'done' : 'downloading', percent: videoDone ? 100 : 42, speed: videoDone ? null : 1200000, eta: videoDone ? null : 12, file: videoDone ? videoFile : null, error: null });
      }
      if (path === '/api/media-downloader/files' && method === 'GET') return json(route, videoDone ? [videoFile] : []);
      if (path === '/api/media-downloader/files/video-file/download' && method === 'GET') return route.fulfill({ status: 200, contentType: 'video/mp4', headers: { 'Content-Disposition': 'attachment; filename="Coastal walk.mp4"' }, body: videoBytes });
      if (path === '/api/media-downloader/files/video-file' && method === 'DELETE') { videoDone = false; return route.fulfill({ status: 204 }); }
      if (path.endsWith('/cancel') && method === 'POST') return json(route, {});
    }
    if (path === "/api/tickets/unread-count" && request.method() === "GET") {
      return json(route, { count: [...api.tickets.values()].filter(ticket => ticket.has_unread).length });
    }
    const method = request.method();
    if (path === "/api/tickets" && method === "GET") {
      return json(route, { tickets: [...api.tickets.values()] });
    }
    if (path === "/api/tickets" && method === "POST") {
      const draft = request.postDataJSON() as Pick<StoredTicket, "type" | "title" | "description">;
      const id = Math.max(0, ...api.tickets.keys()) + 1;
      const now = new Date().toISOString();
      const ticket: StoredTicket = { ...draft, id, status: "open", created_at: now, updated_at: now, closed_at: null, has_unread: false, comments: [] };
      api.tickets.set(id, ticket);
      return json(route, { ticket, duplicate: false, group_size: 1 }, 201);
    }
    const ticketMatch = path.match(/^\/api\/tickets\/(\d+)(?:\/(comments|close|reopen))?$/);
    if (ticketMatch) {
      const ticket = api.tickets.get(Number(ticketMatch[1]));
      if (!ticket) return json(route, { detail: `No ticket ${ticketMatch[1]}.` }, 404);
      const action = ticketMatch[2];
      if (method === "GET" && !action) {
        ticket.has_unread = false;
        return json(route, { ticket });
      }
      if (method === "POST") {
        const now = new Date().toISOString();
        if (action === "reopen") {
          if (ticket.status !== "closed" && ticket.status !== "resolved") return json(route, { detail: "Ticket is already active." }, 400);
          ticket.status = "open";
          ticket.closed_at = null;
          ticket.comments ??= [];
          ticket.comments.push({ id: ticket.comments.length + 1, ticket_id: ticket.id, author: "System", author_role: "system", body: "Ticket reopened by the reporter.", created_at: now });
        } else if (action === "close") {
          ticket.status = "closed";
          ticket.closed_at = now;
        } else if (action === "comments") {
          ticket.comments ??= [];
          ticket.comments.push({ id: ticket.comments.length + 1, ticket_id: ticket.id, author: account.username, author_role: "reporter", body: request.postDataJSON().body, created_at: now });
        } else {
          api.unexpected.push(`${method} ${path}`);
          return json(route, { detail: "No route" }, 404);
        }
        ticket.updated_at = now;
        return json(route, { ticket });
      }
    }

    if (method === "GET" && path === "/api/auth/me") {
      return loggedIn ? json(route, account) : json(route, { detail: "Not logged in" }, 401);
    }
    if (method === "POST" && path === "/api/auth/login") {
      const body = request.postDataJSON() as { username: string; password: string };
      if (body.username !== ACCOUNT.username || body.password !== PASSWORD) {
        return json(route, { detail: "Wrong username or password" }, 401);
      }
      loggedIn = true;
      return json(route, account);
    }
    if (path === "/api/account/tuning") {
      if (method === "PUT") {
        const limits = request.postDataJSON();
        if (limits.max_tool_rounds > 15) return json(route, { detail: "max_tool_rounds cannot be above 15" }, 400);
        if (limits.max_output_tokens > 2048) return json(route, { detail: "max_output_tokens cannot be above 2048" }, 400);
        responseLimits = limits;
      }
      if (method === "DELETE") { responseLimits = { max_output_tokens: null, max_tool_rounds: null }; return route.fulfill({ status: 204 }); }
      return json(route, { limits: responseLimits, ceiling: { max_output_tokens: 2048, max_tool_rounds: 15 } });
    }
    if (path === "/api/account/triage-strategy" && ["GET", "PUT"].includes(method)) {
      if (method === "PUT") api.triageStrategy = request.postDataJSON().value;
      return json(route, { value: api.triageStrategy, default: "auto", strategies: ["english-only", "typed-only", "auto"] });
    }
    if (method === "GET" && path === "/api/settings") {
      return json(route, { force_tool_approval: api.settings.forceToolApproval, calendar_inapp: true, calendar_email: true, calendar_push: false });
    }
    if (method === "PUT" && path === "/api/admin/settings/force_tool_approval") {
      const { value } = request.postDataJSON() as { value: boolean };
      api.settings.forceToolApproval = value;
      return json(route, { force_tool_approval: value });
    }

    // The Admin page: overview counts, the accounts list and deleting one.
    if (method === "GET" && path === "/api/admin/summary") {
      const all = [...api.accounts.values()];
      return json(route, {
        accounts: all.length,
        unverified: all.filter((a) => !a.email_verified).length,
        disabled: all.filter((a) => !a.is_active).length,
        open_invites: 0,
        roles: api.roles.size,
      });
    }
    if (method === "GET" && path === "/api/admin/accounts") {
      const q = (url.searchParams.get("q") ?? "").toLowerCase();
      const all = [...api.accounts.values()].filter((a) => !q || `${a.username} ${a.email}`.toLowerCase().includes(q));
      return json(route, all);
    }
    const accountPath = /^\/api\/admin\/accounts\/(\d+)$/.exec(path);
    if (method === "DELETE" && accountPath) {
      const id = Number(accountPath[1]);
      if (!api.accounts.has(id)) return json(route, { detail: "Account not found" }, 404);
      api.accounts.delete(id);
      return route.fulfill({ status: 204, body: "" });
    }
    if (method === "GET" && path === "/api/admin/roles") return json(route, [...api.roles.values()]);
    const rolePath = /^\/api\/admin\/roles\/(\d+)$/.exec(path);
    if (method === "DELETE" && rolePath) {
      if (!api.roles.delete(Number(rolePath[1]))) return json(route, { detail: "Role not found" }, 404);
      return route.fulfill({ status: 204, body: "" });
    }
    if (method === "GET" && path === "/api/admin/permissions") return json(route, ADMIN_PERMISSIONS);
    if (method === "GET" && path === "/api/admin/invites") return json(route, []);
    if (method === "GET" && path === "/api/agent") return json(route, ENTRY_AGENT);
    if (method === "GET" && path === "/api/agents") {
      return json(route, [{ ...ENTRY_AGENT, entry: true, orchestrator: true, focus: "General questions.", status: "running", provider: "anthropic", gateway: null, model: null }]);
    }
    // The predicted next prompt: the fake has none to offer. And the account switch for it.
    if (method === "GET" && /^\/api\/chats\/[^/]+\/suggestion$/.test(path)) return json(route, { text: null });
    if (method === "PATCH" && path === "/api/account/preferences") {
      return json(route, { ...account, ...(request.postDataJSON() as Record<string, unknown>) });
    }

    // The agent's clickable questions: the fake never asks one (its stream is a finished body), so any answer is refused.
    if (method === "POST" && /^\/api\/chats\/[^/]+\/questions$/.test(path)) {
      return json(route, { detail: "Nothing is waiting for that answer" }, 409);
    }
    if (method === "GET" && path === "/api/chats") return json(route, [...api.chats.values()].map(summary));
    // Deleting every chat, or one.
    if (method === "DELETE" && path === "/api/chats") {
      api.chats.clear();
      return route.fulfill({ status: 204, body: "" });
    }

    // The Capabilities page: the list, the on/off switch, and (through MCP below) the tools each one offers.
    if (method === "GET" && path === "/api/capabilities") return json(route, [...api.capabilities.values()]);
    const capabilityPath = /^\/api\/capabilities\/([a-z_]+)$/.exec(path);
    if (method === "PATCH" && capabilityPath) {
      const found = api.capabilities.get(capabilityPath[1]!);
      if (!found) return json(route, { detail: "Capability not found" }, 404);
      found.enabled = (request.postDataJSON() as { enabled: boolean }).enabled;
      return json(route, found);
    }
    if (method === "GET" && path === "/api/account-agents") return json(route, { disabled: [...api.disabledAgents].sort() });
    const accountAgent = /^\/api\/account-agents\/([A-Za-z0-9_.-]+)$/.exec(path);
    if (method === "PUT" && accountAgent) {
      if ((request.postDataJSON() as { enabled: boolean }).enabled) api.disabledAgents.delete(accountAgent[1]!);
      else api.disabledAgents.add(accountAgent[1]!);
      return json(route, { disabled: [...api.disabledAgents].sort() });
    }
    if (method === "GET" && path === "/api/extensions") return json(route, []);

    // The account's private extensions: a saved one is reported connected with one tool.
    if (method === "GET" && path === "/api/user-extensions") return json(route, [...api.userExtensions.values()]);
    if (method === "POST" && path === "/api/user-extensions") {
      const body = request.postDataJSON() as { label: string; url: string; description?: string; headers?: Record<string, string> };
      const id = body.label.toLowerCase().replace(/[^a-z0-9]+/g, "") || "ext";
      if (api.userExtensions.has(id)) return json(route, { detail: "You already have an extension with that name" }, 409);
      const created: StoredUserExtension = {
        id,
        label: body.label,
        description: body.description ?? "",
        url: body.url,
        header_names: Object.keys(body.headers ?? {}),
        enabled: false,
        status: "unknown",
        error: null,
        tools: [],
      };
      api.userExtensions.set(id, created);
      return json(route, created, 201);
    }
    const userExtPath = /^\/api\/user-extensions\/([A-Za-z0-9_.-]+)$/.exec(path);
    if (userExtPath) {
      const found = api.userExtensions.get(userExtPath[1]!);
      if (!found) return json(route, { detail: "Extension not found" }, 404);
      if (method === "DELETE") {
        api.userExtensions.delete(found.id);
        return route.fulfill({ status: 204, body: "" });
      }
      if (method === "PATCH") {
        const patch = request.postDataJSON() as Partial<StoredUserExtension> & { headers?: Record<string, string> };
        if (patch.label !== undefined) found.label = patch.label;
        if (patch.url !== undefined) found.url = patch.url;
        if (patch.description !== undefined) found.description = patch.description;
        if (patch.headers !== undefined) found.header_names = Object.keys(patch.headers);
        if (patch.enabled !== undefined) found.enabled = patch.enabled;
        // Once on, the probe finds its tool; off, nothing is checked.
        found.status = found.enabled ? "connected" : "unknown";
        found.tools = found.enabled ? ["search"] : [];
        return json(route, found);
      }
    }
    if (method === "POST" && path === "/api/mcp/server") return mcpServer(route, api);
    if (method === "GET" && path === "/api/mcp/server") return route.fulfill({ status: 405, body: "" });

    // An account with tools.use also asks for the slash commands; none are offered here.
    if (method === "GET" && path === "/api/commands") return json(route, []);

    // No page is hidden from the sidebar for everyone.
    if (method === "GET" && path === "/api/settings/pages") return json(route, { hidden: [] });

    // The nav rail arrangement: the default one (nothing saved).
    if (method === "GET" && path === "/api/nav-preferences") return json(route, { order: [], pinned: [], hidden: [] });

    // The member's saved prompts: none unless a test adds them.
    if (method === "GET" && path === "/api/templates") return json(route, [...api.templates.values()]);
    const templatePath = /^\/api\/templates\/(\d+)$/.exec(path);
    if (method === "DELETE" && templatePath) {
      if (!api.templates.delete(Number(templatePath[1]))) return json(route, { detail: "Prompt not found" }, 404);
      return route.fulfill({ status: 204, body: "" });
    }

    // Typed questions to the Triage Assistant. The fake writes a title from each description's first word
    // and answers the first option (or yes) every time.
    if (path === "/api/triage/titles" && method === "POST") {
      const { descriptions } = request.postDataJSON() as { descriptions: string[] };
      const titles = descriptions.map((d, i) => d.toLowerCase().match(/[a-z0-9]+/)?.[0] ?? `option${i + 1}`);
      return json(route, { titles: titles.map((t, i) => (titles.indexOf(t) === i ? t : `${t}${i + 1}`)) });
    }
    if (path === "/api/triage/ask" && method === "POST") {
      const { kind, options } = request.postDataJSON() as { kind: "choice" | "yes_no"; options: { title: string }[] };
      if (kind === "yes_no") return json(route, { kind, answer: "yes", yes: 0.9, confidence: 0.9, uncertain: false });
      const probabilities = Object.fromEntries(options.map((o, i) => [o.title, i === 0 ? 0.8 : 0.2 / (options.length - 1)]));
      return json(route, { kind, choice: options[0]!.title, probabilities, confidence: 0.8, uncertain: false });
    }

    if (method === "POST" && path === "/api/brains/browse") return json(route, {
      message: "This brain is not configured.", status: "not_configured", index_status: "not_started"
    });
    if (method === "GET" && path.startsWith("/api/brains/connections/")) return json(route, {
      id: null, scope: path.endsWith("instance") ? "instance" : "personal", label: "Brain", endpoint: "", folder: "Inbox",
      enabled: false, allow_write: false, credential_configured: false, revision: 0, generation: null, status: "not_configured"
    });
    if (method === "GET" && ["/api/brains/destinations", "/api/brains/suggestions", "/api/brains/promotions"].includes(path)) return json(route, []);
    // Laya's tag suggestions. The fake "reads" the note: it suggests the account's tags that the text mentions.
    if (path === "/api/notes/suggest-tags" && method === "POST") {
      const { title, body, tags } = request.postDataJSON() as NoteBody;
      const have = new Set(tags ?? []);
      const used = new Set([...api.notes.values()].flatMap((n) => n.tags));
      const text = `${title ?? ""} ${body ?? ""}`.toLowerCase();
      const suggested = [...used].filter((tag) => !have.has(tag) && text.includes(tag)).sort();
      return json(route, { suggested, checked: [...used].filter((tag) => !have.has(tag)).length, skipped: 0 });
    }

    if (path === "/api/memory" && method === "GET") return json(route, [...api.memories.values()].sort((a, b) => b.id - a.id));
    if (path === "/api/memory" && method === "POST") {
      const { text } = route.request().postDataJSON() as { text: string };
      const existing = [...api.memories.values()].find((memory) => memory.text.toLowerCase() === text.toLowerCase());
      if (existing) return json(route, existing, 201);
      const id = Math.max(0, ...api.memories.keys()) + 1;
      const memory = { id, text, created_at: new Date().toISOString() };
      api.memories.set(id, memory);
      return json(route, memory, 201);
    }
    const memoryPath = /^\/api\/memory\/(\d+)$/.exec(path);
    if (memoryPath && (method === "PUT" || method === "DELETE")) {
      const id = Number(memoryPath[1]);
      const memory = api.memories.get(id);
      if (!memory) return json(route, { detail: "Memory not found" }, 404);
      if (method === "DELETE") { api.memories.delete(id); return route.fulfill({ status: 204 }); }
      const body = route.request().postDataJSON() as { text: string; expected_text: string };
      if (body.expected_text !== memory.text) return json(route, { detail: "Memory changed. Reload and try again." }, 409);
      memory.text = body.text;
      return json(route, memory);
    }

    // The tag-writer's proposal: the fake writes one tag from the note's first word.
    if (path === "/api/notes/generate-tag" && method === "POST") {
      const { title, body, tags } = request.postDataJSON() as NoteBody;
      const word = `${title ?? ""} ${body ?? ""}`.toLowerCase().match(/[a-z0-9]{3,}/)?.[0];
      return json(route, { tags: word && !(tags ?? []).includes(word) ? [word] : [] });
    }

    // Private notes, newest edit first. Ids are 32 hex characters, as ember_api makes them.
    if (path === "/api/notes" && (method === "GET" || method === "POST")) {
      if (method === "GET") return json(route, [...api.notes.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
      const { title, body, tags, agent_readable } = request.postDataJSON() as NoteBody;
      if (!title?.trim()) return json(route, { detail: "String should have at least 1 character" }, 422);
      const id = (api.notes.size + 1).toString(16).padStart(32, "0");
      const now = new Date().toISOString().slice(0, 19);
      const note = {
        id, title: title.trim(), body: body ?? "", tags: tags ?? [], agent_readable: agent_readable ?? false,
        last_editor: "user" as const, created_at: now, updated_at: now,
      };
      api.notes.set(id, note);
      return json(route, note, 201);
    }
    const notePath = /^\/api\/notes\/([0-9a-f]{32})$/.exec(path);
    if (notePath) {
      const note = api.notes.get(notePath[1]!);
      if (!note) return json(route, { detail: "Note not found" }, 404);
      if (method === "GET") return json(route, note);
      if (method === "DELETE") {
        api.notes.delete(note.id);
        return route.fulfill({ status: 204, body: "" });
      }
      if (method === "PUT") {
        const { title, body, tags, agent_readable, expected_updated_at } = request.postDataJSON() as NoteBody;
        // A save that names the version it opened is refused when the note changed since, as ember_api does.
        if (expected_updated_at !== undefined && expected_updated_at !== note.updated_at) {
          return json(route, { detail: "This note changed since you opened it" }, 412);
        }
        // PUT replaces every field: one left out is reset, as ember_api does.
        Object.assign(note, {
          title: title.trim(), body: body ?? "", tags: tags ?? [], agent_readable: agent_readable ?? false,
          last_editor: "user", updated_at: new Date().toISOString().slice(0, 19),
        });
        return json(route, note);
      }
    }

    // Read-only chat links: listing them for one chat, and turning one off.
    if (method === "GET" && path === "/api/shares") {
      const chatId = url.searchParams.get("chat_id");
      return json(route, [...api.shares.values()].filter((s) => !chatId || s.chat_id === chatId));
    }
    const sharePath = /^\/api\/shares\/(\d+)$/.exec(path);
    if (method === "DELETE" && sharePath) {
      if (!api.shares.delete(Number(sharePath[1]))) return json(route, { detail: "Link not found" }, 404);
      return route.fulfill({ status: 204, body: "" });
    }

    // No limits are set, so the sidebar shows no usage gauge.
    if (method === "GET" && path === "/api/usage") {
      const groupBy = url.searchParams.get("group_by") ?? "agent";
      const keys = groupBy === "model" ? ["priced-model", "unknown-model"] : groupBy === "provider" ? ["example", "unknown"] : groupBy === "gateway" ? ["direct", "unknown"] : ["main", "helper"];
      return json(route, { ...USAGE, report: { ...USAGE.report, group_by: groupBy,
        groups: USAGE.report.groups.map((g, i) => ({ ...g, key: keys[i] })) } });
    }
    if (method === "GET" && path === "/api/usage/records") return json(route, USAGE.report.by_agent.map((a, i) => ({
      id: i + 1, turn_id: "example-turn", kind: "chat", chat_id: null,
      agent: a.agent, agent_id: a.agent, provider_id: i ? "unknown" : "example", gateway: null,
      model: a.model, input_tokens: i ? 400 : 800, output_tokens: i ? 100 : 200,
      total_tokens: a.tokens, cost: a.cost, delegated_by: i ? "main" : null,
      started_at: "2026-10-18T09:00:00", finished_at: "2026-10-18T09:00:01", created_at: "2026-10-18T09:00:01",
    })));

    // The agent's MCP endpoint: only its `status` tool is called by the page.
    if (method === "POST" && path === "/api/mcp/agents/agent-1") return mcpAgent(route);
    // The page also tries to open a notification stream; "not offered" is a valid answer.
    if (method === "GET" && path === "/api/mcp/agents/agent-1") return route.fulfill({ status: 405, body: "" });

    // Chat folders, as ember_api keeps them: names unique per account (any
    // case), and deleting a folder deletes every chat in it, pinned or not.
    if (method === "GET" && path === "/api/chat-folders") {
      return json(route, [...api.folders.values()].map((f) => ({ ...f, chat_count: chatsIn(api, f.id) })));
    }
    if (method === "POST" && path === "/api/chat-folders") {
      const { name } = request.postDataJSON() as { name: string };
      if ([...api.folders.values()].some((f) => f.name.toLowerCase() === name.toLowerCase())) {
        return json(route, { detail: "A folder with that name already exists" }, 409);
      }
      const id = Math.max(0, ...api.folders.keys()) + 1;
      api.folders.set(id, { id, name, position: id });
      return json(route, { id, name, position: id, chat_count: 0 }, 201);
    }
    const folderPath = /^\/api\/chat-folders\/(\d+)$/.exec(path);
    if (folderPath) {
      const id = Number(folderPath[1]);
      const found = api.folders.get(id);
      if (!found) return json(route, { detail: "Folder not found" }, 404);
      if (method === "PATCH") {
        const body = request.postDataJSON() as { name?: string; position?: number };
        if (body.name !== undefined) found.name = body.name;
        if (body.position !== undefined) found.position = body.position;
        return json(route, { ...found, chat_count: chatsIn(api, id) });
      }
      if (method === "DELETE") {
        for (const [chatId, c] of api.chats) if (c.folder_id === id) api.chats.delete(chatId);
        api.folders.delete(id);
        return route.fulfill({ status: 204, body: "" });
      }
    }

    if (method === "GET" && path === "/api/chats/second-brain") {
      return json(route, { available: api.capabilities.get("obsidian")?.enabled === true });
    }
    const chatPath = /^\/api\/chats\/([A-Za-z0-9-]+)(\/[a-z]+)?$/.exec(path);
    if (chatPath) {
      const [, id, tail] = chatPath;
      if (method === "PATCH" && !tail) {
        const chat = api.chats.get(id!);
        if (!chat) return json(route, { detail: "Chat not found" }, 404);
        const body = request.postDataJSON() as { title?: string; folder_id?: number | null; pinned?: boolean; save_to_second_brain?: boolean };
        if (body.save_to_second_brain !== undefined) chat.save_to_second_brain = body.save_to_second_brain;
        if (body.title !== undefined) chat.title = body.title;
        if ("folder_id" in body) chat.folder_id = body.folder_id ?? null;
        if (body.pinned !== undefined) chat.pinned = body.pinned;
        return json(route, summary(chat));
      }
      if (method === "DELETE" && !tail) {
        if (!api.chats.delete(id!)) return json(route, { detail: "Chat not found" }, 404);
        return route.fulfill({ status: 204, body: "" });
      }
      if (method === "GET" && !tail) {
        const chat = api.chats.get(id!);
        return chat ? json(route, { ...summary(chat), messages: chat.messages }) : json(route, { detail: "Not found" }, 404);
      }
      if (method === "POST" && tail === "/turns") return startTurn(route, api, id!);
      if (method === "GET" && tail === "/events") return streamTurn(route, api, id!);
    }

    if (path.startsWith("/api/calendar")) {
      const cal = api.calendar;
      if (path === "/api/calendar/feeds" && method === "GET") return json(route, cal.feeds);
      if (path === "/api/calendar/feeds" && method === "POST") {
        const body = request.postDataJSON() as { name: string; color: string };
        const feed = { id: `f${cal.feeds.length + 1}`, name: body.name, color: body.color, enabled: true, last_fetch_at: null, last_error: null };
        cal.feeds.push(feed);
        return json(route, feed, 201);
      }
      const feedMatch = path.match(/^\/api\/calendar\/feeds\/([a-z0-9]+)$/);
      if (feedMatch && method === "PATCH") {
        const feed = cal.feeds.find((f) => f.id === feedMatch[1]);
        if (!feed) return json(route, { detail: "No such calendar" }, 404);
        const body = request.postDataJSON() as Partial<CalendarFeedStub> & { url?: string };
        for (const key of ["name", "color", "enabled"] as const) {
          if (body[key] !== undefined) Object.assign(feed, { [key]: body[key] });
        }
        return json(route, feed);
      }
      if (feedMatch && method === "DELETE") {
        cal.feeds = cal.feeds.filter((f) => f.id !== feedMatch[1]);
        return route.fulfill({ status: 204 });
      }
      if (path === "/api/calendar/events" && method === "GET") {
        // The initial Work week view hides weekends; keep the fixture inside its requested weekdays.
        const start = new Date(url.searchParams.get("from")!);
        while (start.getDay() === 0 || start.getDay() === 6) start.setDate(start.getDate() + 1);
        start.setHours(10, 0, 0, 0);
        const end = new Date(start.getTime() + 3600_000);
        return json(route, {
          events: cal.feeds.length ? [{ uid: "e1", title: "Standup", start: start.toISOString(), end: end.toISOString(), all_day: false, location: "Room 1", description: "Agenda", sources: [{ name: cal.feeds[0]!.name, color: cal.feeds[0]!.color }] }] : [],
          errors: [],
        });
      }
      if (path === "/api/calendar/alarms" && method === "GET") return json(route, cal.rules);
      if (path === "/api/calendar/alarms" && method === "POST") {
        const body = request.postDataJSON() as { channel: string; lead_minutes: number };
        const rule = { id: `r${cal.rules.length + 1}`, channel: body.channel, lead_minutes: body.lead_minutes, enabled: true };
        cal.rules.push(rule);
        return json(route, rule, 201);
      }
      const ruleMatch = path.match(/^\/api\/calendar\/alarms\/([a-z0-9]+)$/);
      if (ruleMatch && method === "PATCH") {
        const rule = cal.rules.find((r) => r.id === ruleMatch[1]);
        if (!rule) return json(route, { detail: "No such alert" }, 404);
        Object.assign(rule, request.postDataJSON() as Partial<Omit<RuleStub, "id">>);
        return json(route, rule);
      }
      if (ruleMatch && method === "DELETE") {
        cal.rules = cal.rules.filter((r) => r.id !== ruleMatch[1]);
        return route.fulfill({ status: 204 });
      }
      if (path === "/api/calendar/push/key" && method === "GET") return json(route, { key: "A".repeat(87) });
      if (["/api/calendar/push/subscribe", "/api/calendar/push/unsubscribe"].includes(path) && method === "POST") {
        return route.fulfill({ status: 204 });
      }
      if (path === "/api/calendar/prefs") return json(route, { timezone: "UTC", saved: true });
      if (path === "/api/calendar/alerts" && method === "GET") return json(route, cal.alerts);
      const seenMatch = path.match(/^\/api\/calendar\/alerts\/([a-z0-9-]+)\/seen$/);
      if (seenMatch && method === "POST") {
        cal.alerts = cal.alerts.filter((a) => a.id !== seenMatch[1]);
        return route.fulfill({ status: 204 });
      }
    }

    api.unexpected.push(`${method} ${path}`);
    return json(route, { detail: "not part of the fake" }, 404);
  });

  return api;
}

function chatsIn(api: FakeApi, folderId: number): number {
  return [...api.chats.values()].filter((c) => c.folder_id === folderId).length;
}

function startTurn(route: Route, api: FakeApi, id: string) {
  const body = route.request().postDataJSON() as { question: string; title?: string; truncate_to?: number; save_to_second_brain?: boolean };
  api.turns.push(body);
  // An edited question cuts the chat back to before it (`truncate_to`), as ember_api does.
  const kept = body.truncate_to === undefined ? [] : (api.chats.get(id)?.messages.slice(0, body.truncate_to) ?? []);
  api.chats.set(id, {
    id,
    title: body.title ?? api.chats.get(id)?.title ?? body.question,
    agent_id: ENTRY_AGENT.id, // what ember_api reports: the browser sends no agent
    messages: [...kept, { role: "user", content: body.question }],
    running: true,
    save_to_second_brain: body.save_to_second_brain ?? api.chats.get(id)?.save_to_second_brain ?? false,
  });
  return json(route, { chat: summary(api.chats.get(id)!), sequence: 0 }, 202);
}

/** How long the fake delegated agent keeps working before the stream resumes. */
const DELEGATE_WORKING_MS = 1000;

/** The answer streams in two requests, like a connection that drops and resumes
 * from the last sequence: the first ends with the delegated agent working (so the
 * page shows "Test Agent â†’ Calculator" for a moment), the second finishes it. */
async function streamTurn(route: Route, api: FakeApi, id: string) {
  const chat = api.chats.get(id);
  if (!chat) return json(route, { detail: "No answer is being written for this chat" }, 404);
  const after = Number(new URL(route.request().url()).searchParams.get("after") ?? 0);
  const headers = { "Cache-Control": "no-cache" };
  const sse = (body: string) => route.fulfill({ status: 200, contentType: "text/event-stream", headers, body });

  if (after < 1) {
    return sse(
      event(1, {
        type: "agent_start",
        agent_id: DELEGATE.id,
        agent_label: DELEGATE.label,
        step_id: DELEGATE.step_id,
        at: new Date().toISOString(),
        question: "What is 6 times 7?",
        delegated_by: ENTRY_AGENT.id,
      }),
    );
  }

  await new Promise((resolve) => setTimeout(resolve, DELEGATE_WORKING_MS));
  const answer = {
    role: "assistant",
    content: ANSWER,
    agent: chat.agent_id,
    model: "test-model",
    total_tokens: 120,
    input_tokens: 90,
    output_tokens: 30,
    duration_s: 1.2,
  };
  const body =
    event(2, {
      type: "agent_end",
      agent_id: DELEGATE.id,
      agent_label: DELEGATE.label,
      ok: true,
      step_id: DELEGATE.step_id,
      at: new Date().toISOString(),
    }) +
    ANSWER_PIECES.map((text, i) => event(i + 3, { type: "token", text })).join("") +
    event(ANSWER_PIECES.length + 3, { type: "final", message: answer, cancelled: false });
  // What the page loads once the answer ends: the saved chat, answer included.
  chat.messages = [...chat.messages, answer];
  chat.running = false;
  return sse(body);
}

/** Just enough of MCP over HTTP for the Capabilities page's session with mcp_server: it lists the
 * tools of the capabilities that are on, so switching one changes what the page shows. */
async function mcpServer(route: Route, api: FakeApi) {
  const message = route.request().postDataJSON() as { id?: number; method: string };
  if (message.id === undefined) return route.fulfill({ status: 202, body: "" });
  const tools = [...api.capabilities.values()].filter((c) => c.enabled).flatMap((c) => c.tools);
  let result: unknown = {};
  if (message.method === "initialize") {
    result = { protocolVersion: "2025-06-18", capabilities: { tools: {}, resources: {} }, serverInfo: { name: "fake-server", version: "1" } };
  } else if (message.method === "tools/list") {
    result = { tools: tools.map((name) => ({ name, description: `The ${name} tool.`, inputSchema: { type: "object", properties: {} } })) };
  } else if (message.method === "resources/list") {
    result = { resources: [] };
  } else if (message.method === "resources/templates/list") {
    result = { resourceTemplates: [] };
  }
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "Mcp-Session-Id": "fake-server-session" },
    body: JSON.stringify({ jsonrpc: "2.0", id: message.id, result }),
  });
}

/** Just enough of MCP over HTTP for the page's session with the agent. */
async function mcpAgent(route: Route) {
  const message = route.request().postDataJSON() as { id?: number; method: string };
  if (message.id === undefined) return route.fulfill({ status: 202, body: "" });
  const result =
    message.method === "initialize"
      ? { protocolVersion: "2025-06-18", capabilities: { tools: {} }, serverInfo: { name: "fake-agent", version: "1" } }
      : { content: [{ type: "text", text: JSON.stringify({ available: true }) }], isError: false };
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "Mcp-Session-Id": "fake-session" },
    body: JSON.stringify({ jsonrpc: "2.0", id: message.id, result }),
  });
}

/** Small valid PDF with byte-accurate xref offsets, used for real PDF.js worker previews. */
export function samplePdf(label: string, pageCount = 1): Buffer {
  const kids = Array.from({ length: pageCount }, (_, i) => `${4 + i * 2} 0 R`).join(' ');
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    `<< /Type /Pages /Kids [${kids}] /Count ${pageCount} >>`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  for (let i = 0; i < pageCount; i++) {
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 3 0 R >> >> /Contents ${5 + i * 2} 0 R >>`);
    const stream = `BT /F1 18 Tf 35 340 Td (${label} ${i + 1}) Tj ET`;
    objects.push(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`);
  }
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, i) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${i + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${offsets.length}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  pdf += `trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}
