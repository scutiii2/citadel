import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import ConnectView from "./ConnectView.vue";

const { auth, replace, server } = vi.hoisted(() => ({
  auth: { reset: vi.fn() },
  replace: vi.fn(),
  server: { connectServer: vi.fn(), serverBase: vi.fn(), serverError: vi.fn(), isDesktop: vi.fn(), setSessionToken: vi.fn() },
}));
vi.mock("../../../stores/auth", () => ({ useAuthStore: () => auth }));
vi.mock("vue-router", () => ({ useRoute: () => ({ query: { redirect: "/notes" } }), useRouter: () => ({ replace }) }));
vi.mock("../../../utils/server", () => server);

beforeEach(() => {
  vi.resetAllMocks();
  server.serverBase.mockReturnValue("");
  server.serverError.mockReturnValue("");
  server.isDesktop.mockReturnValue(true);
});

it("stays on the screen and shows the error when the server does not answer", async () => {
  server.connectServer.mockResolvedValue({ ok: false, error: "Could not reach http://x:1." });
  const w = mount(ConnectView);
  await w.get("input").setValue("http://x:1");
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Could not reach http://x:1.");
  expect(w.get("input").attributes("aria-invalid")).toBe("true");
  expect(replace).not.toHaveBeenCalled();
  expect(w.get("button.primary").attributes("aria-busy")).toBe("false");
});

it("goes on to the page it was asked for once the server answers", async () => {
  server.connectServer.mockResolvedValue({ ok: true, origin: "http://x:1" });
  const w = mount(ConnectView);
  await w.get("input").setValue("http://x:1");
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(replace).toHaveBeenCalledWith("/notes");
  expect(server.setSessionToken).toHaveBeenCalledWith("");   // new server: the old session is dropped
  expect(auth.reset).toHaveBeenCalledOnce();
});

it("keeps the session when the same server is checked again", async () => {
  server.serverBase.mockReturnValue("http://x:1");
  server.connectServer.mockResolvedValue({ ok: true, origin: "http://x:1" });
  const w = mount(ConnectView);
  await w.get("form").trigger("submit");
  await flushPromises();
  expect(server.setSessionToken).not.toHaveBeenCalled();
  expect(auth.reset).not.toHaveBeenCalled();
  expect(replace).toHaveBeenCalledWith("/notes");
});

it("shows why the last check failed on arrival, and guards a repeated submit", async () => {
  server.serverError.mockReturnValue("Lost the connection to http://x:1.");
  let finish!: (value: unknown) => void;
  server.connectServer.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const w = mount(ConnectView);
  expect(w.get('[role="alert"]').text()).toBe("Lost the connection to http://x:1.");
  await w.get("input").setValue("http://x:1");
  await w.get("form").trigger("submit");
  await w.get("form").trigger("submit");
  expect(server.connectServer).toHaveBeenCalledOnce();
  expect(w.get("button.primary").attributes("aria-busy")).toBe("true");
  finish({ ok: false, error: "no" }); await flushPromises();
});

it("finishes the example address on Tab and Right arrow, only at the end of a matching text", async () => {
  const w = mount(ConnectView);
  const input = w.get("input");
  await input.trigger("keydown", { key: "ArrowRight" });
  expect((input.element as HTMLInputElement).value).toBe("http://192.168.1.5:29601");
  await input.setValue("");
  await input.trigger("keydown", { key: "Tab" });
  expect((input.element as HTMLInputElement).value).toBe("http://192.168.1.5:29601");
  await input.setValue("http://10.0.0.5");            // does not match the example: Tab keeps its normal job
  await input.trigger("keydown", { key: "Tab" });
  expect((input.element as HTMLInputElement).value).toBe("http://10.0.0.5");
});
