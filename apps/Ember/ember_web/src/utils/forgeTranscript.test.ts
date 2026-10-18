import { describe, expect, it } from "vitest";
import type { ForgeEvent } from "../api/ForgeClient";
import { applyEvent, emptyTranscript, type TranscriptState } from "./forgeTranscript";

const T = "2026-10-18T10:00:00";
const msg = (seq: number, sender: string, kind: string, body: Record<string, unknown>): ForgeEvent =>
  ({ type: "message", seq, sender, kind, body, created_at: T }) as ForgeEvent;
const run = (events: ForgeEvent[], from: TranscriptState = emptyTranscript()) => events.reduce(applyEvent, from);

describe("applyEvent", () => {
  it("shows the user's message", () => {
    const state = run([msg(1, "user", "text", { text: "@claude hi" })]);

    expect(state.cursor).toBe(1);
    expect(state.items).toEqual([{ key: "m1", kind: "user", seq: 1, text: "@claude hi", time: T }]);
  });

  it("streams a reply from deltas, then replaces the draft with the stored message", () => {
    const streaming = run([
      msg(1, "user", "text", { text: "go" }),
      { type: "delta", turn_id: "t1", sender: "7", label: "claude", text: "Hel" },
      { type: "delta", turn_id: "t1", sender: "7", label: "claude", text: "lo" },
    ]);
    const draft = streaming.items[1]!;
    expect(draft).toMatchObject({ kind: "worker", turnId: "t1", label: "claude", text: "Hello", streaming: true, seq: null });

    const done = applyEvent(streaming, msg(2, "7", "text", { text: "Hello there", label: "claude", provider: "claude", turn_id: "t1", usage: { input_tokens: 3, output_tokens: 4 } }));

    expect(done.items).toHaveLength(2);
    expect(done.items[1]).toMatchObject({
      key: "m2", kind: "worker", seq: 2, text: "Hello there", streaming: false, partial: false, provider: "claude",
      usage: { input_tokens: 3, output_tokens: 4 },
    });
  });

  it("shows a stored reply that had no streaming", () => {
    const state = run([msg(1, "7", "text", { text: "Done", label: "codex", provider: "codex", turn_id: "t9" })]);

    expect(state.items[0]).toMatchObject({ kind: "worker", label: "codex", provider: "codex", text: "Done", streaming: false, usage: null });
  });

  it("marks a draft partial when the turn ends without a reply", () => {
    const state = run([
      { type: "turn", running: true },
      { type: "delta", turn_id: "t1", sender: "7", label: "claude", text: "Half" },
      { type: "turn", running: false },
    ]);

    expect(state.running).toBe(false);
    expect(state.items[0]).toMatchObject({ streaming: false, partial: true, text: "Half" });
  });

  it("lists tool calls", () => {
    const state = run([msg(2, "7", "tool", { label: "claude", name: "Edit", summary: "app.py", turn_id: "t1" })]);

    expect(state.items[0]).toEqual({ key: "m2", kind: "tool", seq: 2, label: "claude", name: "Edit", summary: "app.py" });
  });

  it("tracks a permission request through its answer", () => {
    const asked = run([msg(3, "7", "permission_request", { request_id: "r1", turn_id: "t1", label: "claude", tool: "Bash", summary: "npm test" })]);
    expect(asked.items[0]).toMatchObject({ kind: "permission", requestId: "r1", status: "pending", tool: "Bash", summary: "npm test" });

    const allowed = applyEvent(asked, msg(4, "user", "permission_result", { request_id: "r1", allow: true, by: "user" }));
    expect(allowed.items).toHaveLength(1);
    expect(allowed.items[0]).toMatchObject({ status: "allowed" });

    const denied = applyEvent(asked, msg(4, "user", "permission_result", { request_id: "r1", allow: false, by: "user" }));
    expect(denied.items[0]).toMatchObject({ status: "denied" });

    const expired = applyEvent(asked, msg(4, "system", "permission_result", { request_id: "r1", allow: false, by: "timeout" }));
    expect(expired.items[0]).toMatchObject({ status: "timed_out" });
  });

  it("ignores a permission result for a request it never saw", () => {
    const state = run([msg(4, "user", "permission_result", { request_id: "ghost", allow: true, by: "user" })]);

    expect(state.items).toEqual([]);
    expect(state.cursor).toBe(4);
  });

  it("shows system notes", () => {
    expect(run([msg(1, "system", "system", { text: "@claude is offline." })]).items[0]).toEqual({
      key: "m1", kind: "system", seq: 1, text: "@claude is offline.",
    });
  });

  it("ignores messages it already has, so a replay changes nothing", () => {
    const once = run([msg(1, "user", "text", { text: "a" }), msg(2, "user", "text", { text: "b" })]);

    const again = run([msg(2, "user", "text", { text: "b" }), msg(1, "user", "text", { text: "a" })], once);

    expect(again).toBe(once);
  });

  it("keeps the state when the turn flag does not change, and ignores pings and lag notices", () => {
    const state = run([{ type: "turn", running: true }]);

    expect(applyEvent(state, { type: "turn", running: true })).toBe(state);
    expect(applyEvent(state, { type: "ping" })).toBe(state);
    expect(applyEvent(state, { type: "lagged" })).toBe(state);
  });

  it("never mutates the state it is given", () => {
    const before = run([msg(1, "user", "text", { text: "a" })]);
    const snapshot = JSON.stringify(before);

    applyEvent(before, msg(2, "user", "text", { text: "b" }));
    applyEvent(before, { type: "delta", turn_id: "t", sender: "1", label: "x", text: "y" });

    expect(JSON.stringify(before)).toBe(snapshot);
  });

  it("ignores a message kind it does not know", () => {
    const state = run([msg(1, "user", "carrier-pigeon", { text: "coo" })]);

    expect(state.items).toEqual([]);
    expect(state.cursor).toBe(1);
  });
});
