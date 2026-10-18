import type { ForgeDeltaEvent, ForgeEvent, ForgeMessageEvent } from "../api/ForgeClient";

/** What the transcript shows, built from the event stream. Pure: every function returns new values. */

export type PermissionStatus = "pending" | "allowed" | "denied" | "timed_out";

export interface UserItem {
  key: string;
  kind: "user";
  seq: number;
  text: string;
  time: string;
}
export interface WorkerItem {
  key: string;
  kind: "worker";
  /** Null while it is a streaming draft. */
  seq: number | null;
  turnId: string;
  label: string;
  provider: string | null;
  text: string;
  streaming: boolean;
  /** A draft whose turn ended without a stored reply. */
  partial: boolean;
  time: string | null;
  usage: { input_tokens: number; output_tokens: number } | null;
}
export interface ToolItem {
  key: string;
  kind: "tool";
  seq: number;
  label: string;
  name: string;
  summary: string;
}
export interface PermissionItem {
  key: string;
  kind: "permission";
  seq: number;
  requestId: string;
  turnId: string;
  label: string;
  tool: string;
  summary: string;
  status: PermissionStatus;
}
export interface SystemItem {
  key: string;
  kind: "system";
  seq: number;
  text: string;
}
export type TranscriptItem = UserItem | WorkerItem | ToolItem | PermissionItem | SystemItem;

export interface TranscriptState {
  items: TranscriptItem[];
  /** The newest stored message seen. */
  cursor: number;
  running: boolean;
}

export const emptyTranscript = (): TranscriptState => ({ items: [], cursor: 0, running: false });

const text = (value: unknown): string => (typeof value === "string" ? value : "");

export function applyEvent(state: TranscriptState, event: ForgeEvent): TranscriptState {
  switch (event.type) {
    case "turn":
      if (state.running === event.running) return state;
      return { ...state, running: event.running, items: event.running ? state.items : settleDrafts(state.items) };
    case "delta":
      return appendDelta(state, event);
    case "message":
      return event.seq <= state.cursor ? state : addMessage({ ...state, cursor: event.seq }, event);
    default:
      return state;
  }
}

function settleDrafts(items: TranscriptItem[]): TranscriptItem[] {
  if (!items.some((item) => item.kind === "worker" && item.streaming)) return items;
  return items.map((item) => (item.kind === "worker" && item.streaming ? { ...item, streaming: false, partial: true } : item));
}

function draftIndex(items: TranscriptItem[], turnId: string): number {
  return items.findIndex((item) => item.kind === "worker" && item.seq === null && item.turnId === turnId);
}

function appendDelta(state: TranscriptState, event: ForgeDeltaEvent): TranscriptState {
  const at = draftIndex(state.items, event.turn_id);
  if (at >= 0) {
    const draft = state.items[at] as WorkerItem;
    const items = state.items.slice();
    items[at] = { ...draft, text: draft.text + event.text };
    return { ...state, items };
  }
  const draft: WorkerItem = {
    key: `d${event.turn_id}`,
    kind: "worker",
    seq: null,
    turnId: event.turn_id,
    label: event.label,
    provider: null,
    text: event.text,
    streaming: true,
    partial: false,
    time: null,
    usage: null,
  };
  return { ...state, items: [...state.items, draft] };
}

function addMessage(state: TranscriptState, event: ForgeMessageEvent): TranscriptState {
  const body = event.body;
  const key = `m${event.seq}`;
  switch (event.kind) {
    case "text":
      return event.sender === "user"
        ? push(state, { key, kind: "user", seq: event.seq, text: text(body.text), time: event.created_at })
        : withReply(state, event);
    case "tool":
      return push(state, { key, kind: "tool", seq: event.seq, label: text(body.label), name: text(body.name), summary: text(body.summary) });
    case "permission_request":
      return push(state, {
        key, kind: "permission", seq: event.seq, requestId: text(body.request_id), turnId: text(body.turn_id),
        label: text(body.label), tool: text(body.tool), summary: text(body.summary), status: "pending",
      });
    case "permission_result":
      return resolvePermission(state, text(body.request_id), body.allow === true, text(body.by));
    case "system":
      return push(state, { key, kind: "system", seq: event.seq, text: text(body.text) });
    default:
      return state;
  }
}

function push(state: TranscriptState, item: TranscriptItem): TranscriptState {
  return { ...state, items: [...state.items, item] };
}

function withReply(state: TranscriptState, event: ForgeMessageEvent): TranscriptState {
  const body = event.body;
  const usage = body.usage as { input_tokens?: number; output_tokens?: number } | undefined;
  const reply: WorkerItem = {
    key: `m${event.seq}`,
    kind: "worker",
    seq: event.seq,
    turnId: text(body.turn_id),
    label: text(body.label),
    provider: text(body.provider) || null,
    text: text(body.text),
    streaming: false,
    partial: false,
    time: event.created_at,
    usage: usage ? { input_tokens: usage.input_tokens ?? 0, output_tokens: usage.output_tokens ?? 0 } : null,
  };
  const at = draftIndex(state.items, reply.turnId);
  if (at < 0) return push(state, reply);
  const items = state.items.slice();
  items[at] = reply;
  return { ...state, items };
}

function resolvePermission(state: TranscriptState, requestId: string, allow: boolean, by: string): TranscriptState {
  const at = state.items.findIndex((item) => item.kind === "permission" && item.requestId === requestId);
  if (at < 0) return state;
  const status: PermissionStatus = by === "timeout" ? "timed_out" : allow ? "allowed" : "denied";
  const items = state.items.slice();
  items[at] = { ...(state.items[at] as PermissionItem), status };
  return { ...state, items };
}
