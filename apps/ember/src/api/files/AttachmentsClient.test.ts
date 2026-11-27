import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../http";
import { attachmentsClient } from "./AttachmentsClient";

vi.mock("../http", () => ({ apiRequest: vi.fn() }));

const request = vi.mocked(apiRequest);

describe("attachmentsClient.dictate", () => {
  it("posts WebM bytes and returns the transcript", async () => {
    request.mockResolvedValue({ text: "hello", duration_s: 2 });
    expect(await attachmentsClient.dictate(new Blob(["voice"], { type: "audio/webm" }))).toEqual({ text: "hello", duration_s: 2 });
    expect(request).toHaveBeenCalledWith("POST", "/api/attachments/dictate", { filename: "dictation.webm", data: btoa("voice") }, undefined, undefined);
  });
  it("rejects oversized recordings before upload", async () => {
    const blob = new Blob(["x"]);
    Object.defineProperty(blob, "size", { value: 21 * 1024 * 1024 });
    await expect(attachmentsClient.dictate(blob)).rejects.toThrow("20 MB");
    expect(request).not.toHaveBeenCalled();
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  request.mockResolvedValue({} as never);
});

describe("attachmentsClient.file", () => {
  it("posts any file as base64 to the one upload endpoint", async () => {
    await attachmentsClient.file(new File(["a,b\n1,2\n"], "sales.csv"));

    expect(request).toHaveBeenCalledExactlyOnceWith("POST", "/api/attachments/file", {
      filename: "sales.csv", data: btoa("a,b\n1,2\n"),
    });
  });

  it("refuses a file over the limit before uploading it", async () => {
    const big = new File(["x"], "big.pdf");
    Object.defineProperty(big, "size", { value: 16 * 1024 * 1024 });

    await expect(attachmentsClient.file(big)).rejects.toThrow("Too large");
    expect(request).not.toHaveBeenCalled();
  });
});
