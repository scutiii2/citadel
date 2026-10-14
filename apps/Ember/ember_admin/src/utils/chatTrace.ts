import { parseServerTime } from "./usageFormat";

/** One agent that ran during a chat turn, as ember_api writes it into the entry's details. */
export interface TraceAgent {
  agent_id: string;
  agent_label?: string;
  delegated_by?: string;
  provider_id?: string;
  gateway?: string;
  model?: string;
  model_tier?: string;
  reasoning_effort?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  started_at?: string;
  finished_at?: string;
  tools: string[];
}

export interface TracePrompt {
  messages: { role: string; content: string }[];
  /** Older messages, or part of one, were left out to fit ember_api's size limit. */
  truncated: boolean;
}

export interface AgentRun {
  agent: TraceAgent;
  /** null when the account may not read prompts, or the entry has none. */
  prompt: TracePrompt | null;
  seconds: number | null;
}

function parseJson(text: string | null): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** The agents of a chat-turn entry; empty for older entries that predate the list. */
export function parseTraceAgents(details: string | null): TraceAgent[] {
  const agents = (parseJson(details) as { agents?: unknown } | null)?.agents;
  if (!Array.isArray(agents)) return [];
  return agents
    .filter((a): a is Record<string, unknown> => typeof a === "object" && a !== null && typeof (a as { agent_id?: unknown }).agent_id === "string")
    .map((a) => ({ ...a, tools: Array.isArray(a.tools) ? a.tools.map(String) : [] }) as unknown as TraceAgent);
}

/** One prompt per agent, in the agents' order; empty when hidden or absent. */
export function parsePrompts(text: string | null): TracePrompt[] {
  const value = parseJson(text);
  return Array.isArray(value) ? (value as TracePrompt[]) : [];
}

/** Seconds between two server times, to a tenth; null when either is missing. */
export function durationSeconds(start: string | undefined, end: string | undefined): number | null {
  const span = parseServerTime(end) - parseServerTime(start);
  return Number.isFinite(span) ? Math.round(span / 100) / 10 : null;
}

export function agentRuns(details: string | null, prompts: string | null): AgentRun[] {
  const sent = parsePrompts(prompts);
  return parseTraceAgents(details).map((agent, index) => ({
    agent,
    prompt: sent[index] ?? null,
    seconds: durationSeconds(agent.started_at, agent.finished_at),
  }));
}
