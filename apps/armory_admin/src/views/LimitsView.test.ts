import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { limitsClient, type LimitsView } from "../api/LimitsClient";
import LimitsViewPage from "./LimitsView.vue";

const VIEW: LimitsView = {
  pdf_merger: {
    file_ttl_hours: 6, sweep_interval_minutes: 10, download_link_minutes: 60, mcp_wait_seconds: 100, stored: true,
    limits: { max_file_mb: 100, max_session_mb: 500, max_segments: 50, max_output_pages: 2000, max_image_megapixels: 80, max_concurrent_merges: 2, job_timeout_seconds: 120 },
  },
  media_downloader: {
    file_ttl_hours: 6, sweep_interval_minutes: 10, download_link_minutes: 60, stored: false,
    limits: { max_file_mb: 500, max_duration_minutes: 120, max_session_mb: 2048, max_concurrent_downloads: 2, max_queued_downloads: 8, job_timeout_minutes: 30, max_caller_downloads: 2 },
  },
};

beforeEach(() => {
  vi.spyOn(limitsClient, "get").mockResolvedValue(VIEW);
});
afterEach(() => vi.restoreAllMocks());

async function mounted() {
  const wrapper = mount(LimitsViewPage, { attachTo: document.body });
  await flushPromises();
  return wrapper;
}
const field = (wrapper: Awaited<ReturnType<typeof mounted>>, card: string, key: string) => wrapper.get(`[data-test="card-${card}"] [data-test="${key}"]`);

describe("LimitsView", () => {
  it("shows both capabilities with their values and keeps Save off until something changes", async () => {
    const wrapper = await mounted();
    expect((field(wrapper, "pdf_merger", "max_file_mb").element as HTMLInputElement).value).toBe("100");
    expect((field(wrapper, "media_downloader", "max_file_mb").element as HTMLInputElement).value).toBe("500");
    expect(wrapper.get('[data-test="card-pdf_merger"] [data-test="save"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-test="card-media_downloader"] [data-test="reset"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it("sends only what changed, with caps inside limits", async () => {
    const save = vi.spyOn(limitsClient, "save").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await field(wrapper, "media_downloader", "file_ttl_hours").setValue("12");
    await field(wrapper, "media_downloader", "max_file_mb").setValue("250");
    await wrapper.get('[data-test="card-media_downloader"]').trigger("submit");
    await flushPromises();
    expect(save).toHaveBeenCalledWith("media_downloader", { file_ttl_hours: 12, limits: { max_file_mb: 250 } });
    expect(wrapper.get('[data-test="notice"]').text()).toContain("next start");
    wrapper.unmount();
  });

  it("does not count a value typed back to the saved one as a change", async () => {
    const wrapper = await mounted();
    await field(wrapper, "pdf_merger", "max_segments").setValue("9");
    await field(wrapper, "pdf_merger", "max_segments").setValue("50");
    expect(wrapper.get('[data-test="card-pdf_merger"] [data-test="save"]').attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("resets a changed capability to the defaults", async () => {
    const reset = vi.spyOn(limitsClient, "reset").mockResolvedValue(VIEW);
    const wrapper = await mounted();
    await wrapper.get('[data-test="card-pdf_merger"] [data-test="reset"]').trigger("click");
    await flushPromises();
    expect(reset).toHaveBeenCalledWith("pdf_merger");
    wrapper.unmount();
  });

  it("shows the refusal", async () => {
    vi.spyOn(limitsClient, "save").mockRejectedValue(new Error("mcp_wait_seconds must be between 0 and 100"));
    const wrapper = await mounted();
    await field(wrapper, "pdf_merger", "mcp_wait_seconds").setValue("500");
    await wrapper.get('[data-test="card-pdf_merger"]').trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain("between 0 and 100");
    wrapper.unmount();
  });
});
