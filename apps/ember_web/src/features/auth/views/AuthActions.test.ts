import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import LoginView from "./LoginView.vue";
import RegisterView from "./RegisterView.vue";
import VerifyEmailView from "./VerifyEmailView.vue";
const { auth, replace } = vi.hoisted(() => ({
 auth: { account: { email: "a@example.com" }, login: vi.fn(), register: vi.fn(), verifyEmail: vi.fn(), resendVerification: vi.fn() },
 replace: vi.fn(),
}));
vi.mock("../../../stores/auth", () => ({ useAuthStore: () => auth }));
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace }), RouterLink: { template: "<a><slot /></a>" } }));
beforeEach(() => vi.resetAllMocks());
for (const [name, view, action] of [["login", LoginView, "login"], ["registration", RegisterView, "register"], ["verification", VerifyEmailView, "verifyEmail"]] as const) {
 it(`guards repeated ${name} submissions and announces pending and failure`, async () => {
  let reject!: (error: Error) => void;
  auth[action].mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
  const w = mount(view);
  await w.get("form").trigger("submit");
  await w.get("form").trigger("submit");
  expect(auth[action]).toHaveBeenCalledOnce();
  expect(w.get("button.primary").attributes("aria-busy")).toBe("true");
  expect(w.get("button.primary").text()).toMatch(/Logging|Creating|Verifying/);
  reject(new Error("Try again")); await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Try again");
  expect(w.get("button.primary").attributes("aria-busy")).toBe("false");
  if (name === "verification") {
   expect(w.get("input").attributes("aria-invalid")).toBe("true");
   expect(w.get("input").attributes("aria-describedby")).toBe(w.get('[role="alert"]').attributes("id"));
  }
  w.unmount();
 });
}
it("blocks verification while a resend is pending", async () => {
 let finish!: () => void;
 auth.resendVerification.mockImplementation(() => new Promise<void>(resolve => { finish = resolve; }));
 const w = mount(VerifyEmailView);
 await w.findAll("button").find(b => b.text() === "Send a new code")!.trigger("click");
 await w.get("form").trigger("submit");
 expect(auth.verifyEmail).not.toHaveBeenCalled();
 expect(w.get("button.primary").attributes("aria-busy")).toBe("false");
 expect(w.findAll("button").find(b => b.text() === "Sending…")!.attributes("aria-busy")).toBe("true");
 finish(); await flushPromises();
 expect(w.text()).toContain("A new code is on its way.");
 w.unmount();
});
