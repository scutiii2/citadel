import { mount, flushPromises, type VueWrapper } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/http";
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
  expect(w.findAll("form button.primary").at(-1)!.attributes("aria-busy")).toBe("true");
  // The label stays put while busy (the spinner replaces it in CSS), so the button never resizes.
  expect(w.findAll("form button.primary").at(-1)!.text()).not.toMatch(/Logging|Creating|Verifying/);
  reject(new Error("Try again")); await flushPromises();
  expect(w.get('[role="alert"]').text()).toBe("Try again");
  expect(w.findAll("form button.primary").at(-1)!.attributes("aria-busy")).toBe("false");
  if (name === "verification") {
   expect(w.get("input").attributes("aria-invalid")).toBe("true");
   expect(w.get("input").attributes("aria-describedby")).toBe(w.get('[role="alert"]').attributes("id"));
  }
  w.unmount();
 });
}
it("uses the invited address and opens chat after registration", async () => {
  auth.register.mockResolvedValue({ account: { email_verified: true } });
  const wrapper = mount(RegisterView);

  await wrapper.get("form").trigger("submit");
  await flushPromises();

  expect(replace).toHaveBeenCalledExactlyOnceWith({ name: "chat" });
  expect(wrapper.get(".subtitle").text()).toBe("Registration needs an invite code sent to your email.");
  expect(wrapper.text()).toContain("Use the email address the invite was sent to.");
  wrapper.unmount();
});

function requestCode(wrapper: VueWrapper) {
  return wrapper.findAll("button").find((button) => button.text() === "Email me a code");
}

it("starts without a sent notice, blocks verification while sending, and confirms delivery", async () => {
  let finish!: () => void;
  auth.resendVerification.mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
  const wrapper = mount(VerifyEmailView);

  expect(wrapper.get(".subtitle").text()).toBe("Confirm a@example.com to use Ember.");
  expect(wrapper.text()).not.toContain("A code was sent");
  expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(true);
  const button = requestCode(wrapper);
  expect(button?.classes()).toContain("primary");
  await button!.trigger("click");
  await wrapper.get("form").trigger("submit");

  expect(auth.resendVerification).toHaveBeenCalledOnce();
  expect(auth.verifyEmail).not.toHaveBeenCalled();
  expect(button!.text()).toBe("Sending…");
  expect(button!.attributes("aria-busy")).toBe("true");

  finish();
  await flushPromises();
  expect(wrapper.get('[role="status"]').text()).toBe("A code was sent to a@example.com. It expires in 15 minutes.");
  expect(button!.text()).toBe("Send a new code");
  wrapper.unmount();
});

it.each([
  [429, "Try again in 22 s"],
  [503, "Email could not be sent."],
])("shows the %i response from requesting a verification code and allows retry", async (status, reason) => {
  auth.resendVerification.mockRejectedValue(new ApiError(status, reason));
  const wrapper = mount(VerifyEmailView);
  const button = requestCode(wrapper);
  expect(button?.text()).toBe("Email me a code");

  await button!.trigger("click");
  await flushPromises();

  expect(wrapper.get('[role="alert"]').text()).toBe(reason);
  expect(button!.attributes("disabled")).toBeUndefined();
  expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(true);
  wrapper.unmount();
});
