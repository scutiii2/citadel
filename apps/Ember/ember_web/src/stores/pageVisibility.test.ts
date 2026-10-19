import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account } from "../api/AuthClient";
import { settingsClient } from "../api/SettingsClient";
import { useAuthStore } from "./auth";
import { usePageVisibilityStore } from "./pageVisibility";

vi.mock("../api/SettingsClient", () => ({ settingsClient: { get: vi.fn(), pages: vi.fn() } }));

const ACCOUNT: Account = { id: 1, username: "lex", email: "l@e.com", email_verified: true, roles: [], permissions: [] };

function setup(account: Account | null = ACCOUNT) {
  setActivePinia(createPinia());
  const auth = useAuthStore();
  auth.account = account;
  return { auth, store: usePageVisibilityStore() };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: ["/usage"] });
});

describe("page visibility store", () => {
  it("loads the hidden pages when an account is signed in", async () => {
    const { store } = setup();
    await flushPromises();

    expect(store.hidden).toEqual(["/usage"]);
    expect(store.ready).toBe(true);
  });

  it("loads nothing while signed out", async () => {
    const { store } = setup(null);
    await flushPromises();

    expect(settingsClient.pages).not.toHaveBeenCalled();
    expect(store.hidden).toEqual([]);
  });

  it("treats a failed load as nothing hidden, and is ready", async () => {
    vi.mocked(settingsClient.pages).mockRejectedValue(new Error("down"));
    const { store } = setup();
    await flushPromises();

    expect(store.hidden).toEqual([]);
    expect(store.ready).toBe(true);
  });

  it("drops the list when the account changes and loads the next account's", async () => {
    const { auth, store } = setup();
    await flushPromises();
    vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: ["/agents"] });
    auth.account = { ...ACCOUNT, id: 2 };
    await flushPromises();

    expect(store.hidden).toEqual(["/agents"]);
  });

  it("ignores a late answer for the previous account", async () => {
    let release: (value: { hidden: string[] }) => void = () => {};
    vi.mocked(settingsClient.pages).mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    const { auth, store } = setup();
    vi.mocked(settingsClient.pages).mockResolvedValue({ hidden: ["/agents"] });
    auth.account = { ...ACCOUNT, id: 2 };
    await flushPromises();
    release({ hidden: ["/usage"] });
    await flushPromises();

    expect(store.hidden).toEqual(["/agents"]);
  });

  it("is cleared on logout", async () => {
    const { auth, store } = setup();
    await flushPromises();
    auth.account = null;
    await flushPromises();

    expect(store.hidden).toEqual([]);
    expect(store.ready).toBe(false);
  });
});
