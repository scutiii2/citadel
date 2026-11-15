import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BardAudio from "./BardAudio.vue";

const permissions = vi.hoisted(() => ({ allowed: true }));
vi.mock("../../../stores/auth", () => ({ useAuthStore: () => ({ hasPermission: () => permissions.allowed }) }));

const FID = "a".repeat(32);
const props = { fileId: FID, voice: "en_US-lessac-medium", durationS: 2.04 };

beforeEach(() => {
  permissions.allowed = true;
  // jsdom does not play media.
  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();
});

describe("BardAudio", () => {
  it("streams the file through ember_api, shows its length and voice, and offers the download", () => {
    const wrapper = mount(BardAudio, { props });
    expect(wrapper.get("audio").attributes("src")).toBe(`/api/bard/audio/${FID}`);
    expect(wrapper.get("audio").attributes("controls")).toBeUndefined();
    expect(wrapper.text()).toContain("2.0 s · en_US-lessac-medium");
    expect(wrapper.text()).toContain("0:00 / 0:02");
    expect(wrapper.get("a.save-audio").attributes("href")).toBe(`/api/bard/audio/${FID}`);
  });

  it("hides the download link without the files.download permission but keeps the player", () => {
    permissions.allowed = false;
    const wrapper = mount(BardAudio, { props });
    expect(wrapper.find("audio").exists()).toBe(true);
    expect(wrapper.find("button.play").exists()).toBe(true);
    expect(wrapper.find("a.save-audio").exists()).toBe(false);
  });

  it("plays on the button and follows the audio element's play and pause", async () => {
    const wrapper = mount(BardAudio, { props });
    expect(wrapper.get("button.play").attributes("aria-label")).toBe("Play");
    await wrapper.get("button.play").trigger("click");
    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();

    await wrapper.get("audio").trigger("play");
    expect(wrapper.get("button.play").attributes("aria-label")).toBe("Pause");
    await wrapper.get("audio").trigger("pause");
    expect(wrapper.get("button.play").attributes("aria-label")).toBe("Play");
  });

  it("shows the playback position and seeks from the slider", async () => {
    const wrapper = mount(BardAudio, { props });
    const el = wrapper.get("audio").element as HTMLAudioElement;
    let position = 1.4;
    Object.defineProperty(el, "currentTime", { configurable: true, get: () => position, set: (v: number) => { position = v; } });

    await wrapper.get("audio").trigger("timeupdate");
    expect(wrapper.text()).toContain("0:01 / 0:02");

    await wrapper.get("input.seek").setValue("0.5");
    expect(position).toBe(0.5);
  });

  it("says so when the audio cannot load", async () => {
    const wrapper = mount(BardAudio, { props });
    await wrapper.get("audio").trigger("error");
    expect(wrapper.text()).toContain("Audio unavailable");
    expect(wrapper.find("button.play").exists()).toBe(false);
  });
});
