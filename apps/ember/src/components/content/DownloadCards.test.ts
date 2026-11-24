import { useAuthStore } from "../../stores/auth";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DownloadCards from "./DownloadCards.vue";

const card = (extra = {}) => ({ filename: "report.csv", bytes: 2048, href: "/api/server/download?path=x", label: "EXPORT", ...extra });

describe("DownloadCards", () => {
  it("shows nothing without downloads", () => {
    expect(mount(DownloadCards, { props: { downloads: [] } }).find(".downloads").exists()).toBe(false);
  });

  it("shows a link with the file name and size", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card()] } });

    const link = wrapper.find("a.file");
    expect(link.text()).toBe("⬇ Download report.csv (2 KB)");
    expect(link.attributes("href")).toBe("/api/server/download?path=x");
    expect(link.attributes("download")).toBeDefined();
    expect(wrapper.find(".tag").text()).toBe("EXPORT");
  });

  it("leaves the size out when it is not known", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ bytes: 0 })] } });

    expect(wrapper.find("a.file").text()).toBe("⬇ Download report.csv");
  });

  it("shows a file without a usable link as unavailable, not as a link", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ href: null })] } });

    expect(wrapper.find("a").exists()).toBe(false);
    expect(wrapper.find(".file.unavailable").text()).toBe("report.csv (2 KB) (unavailable)");
  });

  it("shows one card for each download", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card(), card({ filename: "b.txt", label: "DOWNLOAD" })] } });

    expect(wrapper.findAll(".card")).toHaveLength(2);
    expect(wrapper.findAll(".tag").map((t) => t.text())).toEqual(["EXPORT", "DOWNLOAD"]);
  });

  it("shows a file name as text, never as markup", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ filename: "<img src=x onerror=alert(1)>" })] } });

    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.find("a.file").text()).toContain("<img src=x onerror=alert(1)>");
  });
});


beforeEach(() => {
  setActivePinia(createPinia());
  useAuthStore().account = { id: 1, username: "admin", email: "a@example.com", email_verified: true, roles: [], permissions: ["files.download"] };
});

it("does not offer server downloads without files.download", () => {
  useAuthStore().account!.permissions = [];
  const wrapper = mount(DownloadCards, { props: { downloads: [card()] } });
  expect(wrapper.find("a.file").exists()).toBe(false);
});

describe("time left", () => {
  const NOW = Date.UTC(2026, 10, 22, 12, 0, 0);
  const at = (minutes: number) => NOW / 1000 + minutes * 60;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the minutes left", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ expiresAt: at(25) })] } });

    expect(wrapper.find(".left").text()).toBe("Expires in 25 min");
    expect(wrapper.find("a.file").exists()).toBe(true);
  });

  it("counts down as time passes", async () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ expiresAt: at(25) })] } });

    await vi.advanceTimersByTimeAsync(10 * 60 * 1000);

    expect(wrapper.find(".left").text()).toBe("Expires in 15 min");
  });

  it("says Expired and turns the link off after the time passes", async () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ expiresAt: at(1) })] } });

    await vi.advanceTimersByTimeAsync(2 * 60 * 1000);

    expect(wrapper.find(".left").text()).toBe("Expired");
    expect(wrapper.find("a.file").exists()).toBe(false);
    expect(wrapper.find(".file.expired").attributes("aria-disabled")).toBe("true");
  });

  it("shows a card already past its time as expired", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ expiresAt: at(-5) })] } });

    expect(wrapper.find(".left").text()).toBe("Expired");
    expect(wrapper.find("a.file").exists()).toBe(false);
  });

  it("shows no time for a card without an expiry", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card()] } });

    expect(wrapper.find(".left").exists()).toBe(false);
  });

  it("stops its timer when the card goes away", () => {
    const wrapper = mount(DownloadCards, { props: { downloads: [card({ expiresAt: at(25) })] } });

    wrapper.unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
