import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.vue";
import { HostBridge } from "./host/HostBridge";
import { HttpClient } from "./api/http";
import { AscensionClient } from "./api/AscensionClient";
import { CATALOG, PROFILE } from "./api/AscensionClient.fixtures";
import { useSessionStore } from "./stores/session";

beforeEach(() => window.history.replaceState(null, "", "/#ticket=integration-launch"));
afterEach(() => { window.history.replaceState(null, "", "/"); vi.unstubAllGlobals(); });
function setup() {
  const pinia = createPinia(); setActivePinia(pinia);
  const session = useSessionStore(); const postMessage = vi.fn();
  let expired = false;
  const fetchFn = vi.fn<typeof fetch>(async (path, init) => {
    if (path === "/session/redeem") return new Response(JSON.stringify({ token: "integration-session" }));
    if (expired) return new Response(JSON.stringify({ error: "Not signed in" }), { status: 401 });
    if (new Headers(init?.headers).get("Authorization") !== "Bearer integration-session") return new Response("{}", { status: 401 });
    return new Response(JSON.stringify(path === "/ascension/catalog" ? CATALOG : PROFILE));
  });
  session.bridge = new HostBridge({ fetchFn, hostOrigin: "http://127.0.0.1:5173", win: window, parentWin: { postMessage } as unknown as Window });
  session.client = new AscensionClient(new HttpClient(fetchFn, session.bridge, () => session.end()));
  return { session, fetchFn, postMessage, expire: () => { expired = true; } };
}
describe("real host session wiring", () => {
  it("redeems once, loads the save with a bearer session, and tells the host it is ready", async () => {
    const { postMessage, fetchFn } = setup();
    const wrapper = mount(App);
    await flushPromises();
    expect(window.location.hash).toBe("");
    expect(wrapper.find(".collection").exists()).toBe(true);
    expect(wrapper.find('[role="tab"][aria-label="Collection"]').attributes("aria-selected")).toBe("true");
    expect(fetchFn.mock.calls.map(([path]) => path)).toEqual(["/session/redeem", "/ascension/catalog", "/ascension/profile"]);
    expect(postMessage).toHaveBeenCalledWith({ source: "game", type: "ready" }, "http://127.0.0.1:5173");
    expect(wrapper.find("button.close-game").exists()).toBe(false);
    wrapper.unmount();
  });
  it("shows the ended screen when the real transport receives 401", async () => {
    const { session, expire, fetchFn } = setup();
    const wrapper = mount(App); await flushPromises(); expire();
    await expect(session.client!.profile()).rejects.toMatchObject({ status: 401 });
    await flushPromises();
    expect(wrapper.text()).toContain("Session ended, reopen the game from Ember");
    expect(fetchFn.mock.calls.filter(([path]) => path === "/session/redeem")).toHaveLength(1);
    expect(session.bridge!.authHeader()).toEqual({});
    wrapper.unmount();
  });
});

describe("host resize lifecycle", () => {
  it("observes changing game content and disconnects when the view closes", async () => {
    class Observer {
      static instances: Observer[] = [];
      readonly observe = vi.fn();
      readonly disconnect = vi.fn();
      private readonly callback: ResizeObserverCallback;
      constructor(callback: ResizeObserverCallback) { this.callback = callback; Observer.instances.push(this); }
      resize(): void { this.callback([], this as unknown as ResizeObserver); }
    }
    vi.stubGlobal("ResizeObserver", Observer);
    const { postMessage } = setup();
    const wrapper = mount(App); await flushPromises();
    const content = wrapper.find(".main").element;
    const mast = wrapper.find(".mast").element;
    vi.spyOn(mast, "getBoundingClientRect").mockReturnValue({ height: 88 } as DOMRect);
    const observer = Observer.instances[0]!;
    expect(observer.observe).toHaveBeenCalledWith(content);
    expect(observer.observe).toHaveBeenCalledWith(mast);
    Object.defineProperty(content, "scrollHeight", { configurable: true, value: 980 });
    observer.resize();
    expect(postMessage).toHaveBeenCalledWith({ source: "game", type: "resize", height: 1068 }, "http://127.0.0.1:5173");
    Object.defineProperty(content, "scrollHeight", { configurable: true, value: 480 });
    observer.resize();
    expect(postMessage).toHaveBeenCalledWith({ source: "game", type: "resize", height: 568 }, "http://127.0.0.1:5173");
    wrapper.unmount();
    expect(observer.disconnect).toHaveBeenCalledOnce();
  });
});
