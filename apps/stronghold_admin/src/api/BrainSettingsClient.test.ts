import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./http";
import { brainSettingsClient } from "./BrainSettingsClient";

vi.mock("./http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("brainSettingsClient", () => {
  it("reads the settings", async () => {
    await brainSettingsClient.get();
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/api/admin/stronghold-brain-settings");
  });

  it("saves only the changes it is given and returns the new settings", async () => {
    const view = { root: "/data/brain" };
    request.mockResolvedValueOnce(view as never);
    const changes = { long_term: { max_files: 50 }, stack: { warn_ratio: 0.9 } };
    expect(await brainSettingsClient.save(changes)).toBe(view);
    expect(request).toHaveBeenCalledExactlyOnceWith("PUT", "/api/admin/stronghold-brain-settings", changes);
  });
});
