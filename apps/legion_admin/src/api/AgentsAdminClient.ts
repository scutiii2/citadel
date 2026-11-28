import { apiRequest } from "./http";

export interface GatewayInfo {
  id: string;
  label: string;
  model: string;
  tiers: { tier: string; id: string }[];
  /** Decision gateways only: whether confidential data may go to it. */
  trusted?: boolean;
}

/** Provider id -> the gateways it can run through (from ai_agent's gateways/<provider>/<gateway>.json files). */
export type ProviderCatalog = Record<string, GatewayInfo[]>;

interface AgentGatewayChoice {
  gateway: string;
  model?: string;
}

interface AgentLlm {
  provider: string;
  min_confidence?: number;
  gateway?: string;
  model?: string;
  fallback_gateways?: (string | AgentGatewayChoice)[];
  reasoning_effort?: string;
  temperature?: number;
  max_tokens?: number;
  max_tool_rounds?: number;
  max_turn_tokens?: number;
  max_turn_seconds?: number;
  max_effort?: string;
  min_tier?: string;
  max_tier?: string;
  [key: string]: unknown;
}

/** An agent file's content. Fields the form does not edit are kept as they are. */
export interface AgentConfig {
  role: "orchestrator" | "router" | "specialist";
  decision?: Partial<RouterPolicy>;
  label?: string;
  port: number;
  /** Address peers and portcullis reach the agent at; unset = http://127.0.0.1:<port>/mcp. */
  url?: string;
  enabled?: boolean;
  entry?: boolean;
  /** Offer the update_plan checklist tool; on when unset. */
  plan_tool?: boolean;
  /** Suggest a reusable skill after a qualifying task, for the user to approve; off when unset. */
  skill_learning?: boolean;
  llm: AgentLlm;
  persona?: string;
  instructions?: string;
  focus?: string;
  /** Replaces the shared identity line for this agent. */
  identity?: string;
  tools?: { allow?: string[]; deny?: string[] };
  [key: string]: unknown;
}

export interface RouterPolicy {
  choose_agent: boolean;
  choose_tier: boolean;
  min_confidence?: number;
  trace: boolean;
  deadline_seconds: number;
  remote_timeout_seconds: number;
  size_tiers: Record<"tiny" | "everyday" | "large" | "hardest", string>;
}

/** A listed agent: its file plus the id; a file ai_agent could not read has only `error`.
 * `overridden`: this machine's edits replace the tracked default file, which can be reset to. */
export type AgentFile = Partial<AgentConfig> & { id: string; error?: string; overridden?: boolean };

export type AgentStatus = "running" | "offline" | "disabled";

/** A model an agent may run on: its strength tier, model id and what the tier is for. */
export interface AgentTier {
  tier: string;
  id: string;
  use_for: string;
}

/** What portcullis reports about an agent right now. */
export interface LiveAgent {
  status: AgentStatus;
  tiers: AgentTier[];
  decision?: Partial<RouterPolicy> & { fallback_available?: boolean; local_status?: string };
}

/** The prompt texts every agent shares. `overridden` lists the ones that differ from the built-in default. */
export interface SharedPrompts {
  values: Record<string, string>;
  defaults: Record<string, string>;
  overridden: string[];
}

export type ModelGatewayKind = "conversation" | "decision";
/** One input of a gateway's form: [field, label, secret, required]. */
export type ModelGatewayField = [string, string, boolean, boolean];

/** A saved gateway as the page sees it: its settings without secrets (`has_<secret>` says whether one is saved). */
export interface ModelGatewayRow {
  id: string;
  provider?: string;
  kind?: string;
  auth?: string;
  label?: string;
  model?: string;
  timeout_s?: number;
  reachable?: boolean;
  [field: string]: unknown;
}

export interface ModelGatewayList {
  gateways: ModelGatewayRow[];
  presets: Record<string, Record<string, unknown>>;
  /** Chat gateway: provider -> auth variant -> fields. */
  form?: { providers: Record<string, Record<string, ModelGatewayField[]>>; choices: { api: string[] } };
  /** Decision gateway: kind -> fields. */
  kinds?: Record<string, ModelGatewayField[]>;
}

/** One MCP server Legion connects to. A header value is write-only: reads carry `has_value` instead. */
export interface McpOrigin { origin_id: string; origin?: string | null; has_override?: boolean; }

export interface OriginLookup {
  found: boolean;
  origin: string;
  path: string;
  origin_id: string | null;
  group: { service_id: string; name: string } | null;
}

export interface McpServer {
  /** Outside-service form: ids from Treasury's catalog, in the order Legion tries them. */
  service_id?: string;
  path?: string;
  origins?: McpOrigin[];
  /** Sent on save only; Legion registers each address and stores ids. A token is write-only. */
  addresses?: { address: string; name?: string; header_value?: string }[];
  label: string;
  description?: string;
  transport: "http" | "stdio";
  url?: string;
  command?: string;
  args?: string[];
  auth?: { type: string; env_var?: string; header_name?: string; header_value?: string; has_value?: boolean };
}

/** portcullis's /api/admin/agents (needs agents.manage), which ai_agent validates and applies. */
/** What a connection test found: one line (and a code, when it failed) for the whole connection, and one per address when it has several. */
export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  /** Why a failed test failed: an HTTP status (401, 503, ...) or NET, TIME, GONE, STDIO. */
  code?: string;
  origins?: { ok: boolean; message: string; code?: string }[];
}

export const agentsAdminClient = {
  gateways: async () => (await apiRequest<{ providers: ProviderCatalog }>("GET", "/api/admin/agents/gateways")).providers,
  list: async () => (await apiRequest<{ agents: AgentFile[] }>("GET", "/api/admin/agents")).agents,
  create: (id: string, config: AgentConfig) => apiRequest<AgentFile>("POST", "/api/admin/agents", { id, config }),
  update: (id: string, config: AgentConfig) => apiRequest<AgentFile>("PUT", `/api/admin/agents/${encodeURIComponent(id)}`, { config }),
  /** Drops this machine's edits so the tracked default file applies again. */
  reset: (id: string) => apiRequest<AgentFile>("POST", `/api/admin/agents/${encodeURIComponent(id)}/reset`),
  remove: (id: string) => apiRequest<void>("DELETE", `/api/admin/agents/${encodeURIComponent(id)}`),
  modelGateways: (kind: ModelGatewayKind) => apiRequest<ModelGatewayList>("GET", `/api/admin/model-gateways/${kind}`),
  /** Secrets are write-only: leave a secret out to keep the saved one. */
  saveModelGateway: (kind: ModelGatewayKind, id: string, entry: Record<string, unknown>) =>
    apiRequest<ModelGatewayRow>("PUT", `/api/admin/model-gateways/${kind}/${encodeURIComponent(id)}`, entry),
  removeModelGateway: (kind: ModelGatewayKind, id: string) =>
    apiRequest<void>("DELETE", `/api/admin/model-gateways/${kind}/${encodeURIComponent(id)}`),
  /** Without `entry`, tests the saved gateway; with it, the form as filled in, before it is saved. */
  testModelGateway: (kind: ModelGatewayKind, id: string, entry?: Record<string, unknown>) =>
    apiRequest<ConnectionTestResult>("POST", `/api/admin/model-gateways/${kind}/${encodeURIComponent(id)}/test`, entry),
  /** Does each saved address of this MCP server answer? Reads only. */
  testServer: (id: string) => apiRequest<ConnectionTestResult>("POST", `/api/admin/servers/${encodeURIComponent(id)}/test`),
  servers: async () => (await apiRequest<{ servers: Record<string, McpServer> }>("GET", "/api/admin/servers")).servers,
  /** Add or change a server; an auth header sent without its value keeps the saved value. Applies at Legion's next start. */
  /** Does Treasury's outside catalog know this address? Changes nothing. */
  lookupOrigin: (address: string) => apiRequest<OriginLookup>("POST", "/api/admin/servers/lookup", { address }),
  saveServer: (id: string, entry: McpServer) =>
    apiRequest<{ saved: string }>("PUT", `/api/admin/servers/${encodeURIComponent(id)}`, entry),
  removeServer: (id: string) => apiRequest<{ deleted: string }>("DELETE", `/api/admin/servers/${encodeURIComponent(id)}`),
  prompts: () => apiRequest<SharedPrompts>("GET", "/api/admin/agent-prompts"),
  /** `null` (or blank) resets a text to its default. ai_agent restarts every agent to apply it. */
  setPrompts: (changes: Record<string, string | null>) => apiRequest<SharedPrompts>("PUT", "/api/admin/agent-prompts", changes),
  /** The assembled system prompt a draft agent file would get. */
  previewPrompt: async (id: string, config: AgentConfig, caveman: boolean) =>
    (await apiRequest<{ prompt: string }>("POST", "/api/admin/agent-prompt-preview", { id, config, caveman })).prompt,
  /** Status and effective model tiers by agent id (needs chat.use; callers treat a failure as "unknown"). */
  live: async (): Promise<Record<string, LiveAgent>> => {
    const rows = await apiRequest<({ id: string } & LiveAgent)[]>("GET", "/api/agents");
    return Object.fromEntries(rows.map((r) => [r.id, { status: r.status, tiers: r.tiers ?? [], decision: r.decision }]));
  },
};
