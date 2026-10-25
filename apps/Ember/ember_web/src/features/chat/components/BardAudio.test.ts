import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import BardAudio from "./BardAudio.vue";

const permissions = vi.hoisted(() => ({ allowed: true }));
vi.mock("../../../stores/auth", () => ({ useAuthStore: () => ({ hasPermission: () => permissions.allowed }) }));

const FID = "a".repeat(32);

describe("BardAudio", () => {
  it("plays the file through ember_api and offers the download", () => {
    permissions.allowed = true;
    const wrapper = mount(BardAudio, { props: { fileId: FID } });
    const audio = wrapper.get("audio");
    expect(audio.attributes("src")).toBe(`/api/bard/audio/${FID}`);
    expect(audio.attributes("controls")).toBeDefined();
    expect(wrapper.get("a.save-audio").attributes("href")).toBe(`/api/bard/audio/${FID}`);
  });

  it("hides the download link without the files.download permission but keeps the player", () => {
    permissions.allowed = false;
    const wrapper = mount(BardAudio, { props: { fileId: FID } });
    expect(wrapper.find("audio").exists()).toBe(true);
    expect(wrapper.find("a.save-audio").exists()).toBe(false);
  });
});
