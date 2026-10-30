import { apiRequest } from "../../../api/http";

/** running: registered with ai_agent; offline: defined in agents/ but not
 * running; disabled: switched off in its agent file. */
export type AgentStatus = "running" | "offline" | "disabled";

/** One model an agent may run on: its strength tier, model id, and what that
 * tier is meant for. */
export interface ModelTier {
  tier: string;
  id: string;
  use_for: string;
}

/** One agent as ember_api's GET /api/agents returns it. No URL: where the
 * agents live stays server-side. */
export interface AgentListing {
  architect?: { kind: string; workers: string[] } | null;
  internal_role?: "router" | null;
  decision?: { choose_agent?: boolean; choose_tier?: boolean; english?: boolean; typed?: boolean;
    fallback?: boolean; fallback_available?: boolean; deadline_seconds?: number; local_status?: string } | null;
  id: string;
  label: string;
  entry: boolean;
  orchestrator: boolean;
  focus: string;
  status: AgentStatus;
  /** From the agent's `llm` block; null when the agent file does not set it. */
  provider: string | null;
  gateway: string | null;
  model: string | null;
  /** The models its min_tier/max_tier range allows, weakest first; empty when none. */
  tiers: ModelTier[];
}

/** The agents this account switched off, kept in ember_api. Ember leaves them out of its roster. */
export const accountAgentsClient = {
  get: () => apiRequest<{ disabled: string[] }>("GET", "/api/account-agents"),
  set: (agentId: string, enabled: boolean) =>
    apiRequest<{ disabled: string[] }>("PUT", `/api/account-agents/${encodeURIComponent(agentId)}`, { enabled }),
};

export const agentsClient = {
  list: () => apiRequest<AgentListing[]>("GET", "/api/agents"),
};
