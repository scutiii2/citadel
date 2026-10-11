import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it } from "vitest";
import { HostBridge } from "../host/HostBridge";
import { useSessionStore } from "./session";

describe("session lifecycle", () => {
  it("stays ended if the host closes while redemption is in flight", async () => {
    setActivePinia(createPinia());
    const session = useSessionStore();
    window.history.replaceState(null, "", "/#ticket=pending-launch");
    let resolve!: (response: Response) => void;
    const response = new Promise<Response>(done => { resolve = done; });
    session.bridge = new HostBridge({ fetchFn: () => response, hostOrigin: "http://127.0.0.1:5173", win: window, parentWin: null });
    const connecting = session.connect();
    session.end();
    resolve(new Response(JSON.stringify({ token: "late-session" })));
    await connecting;
    expect(session.status).toBe("ended");
    expect(session.bridge.authHeader()).toEqual({});
  });
});
