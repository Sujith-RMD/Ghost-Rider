import { afterEach, expect, test, vi } from "vitest";
import { startAssessment } from "./real-assessment";

afterEach(() => vi.unstubAllGlobals());

test("the selected bytes reach PUT before finalize creates the job", async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const responses = [
    { upload_id: "upload-1", upload_url: "/v1/uploads/upload-1/local", object_key: "uploads/upload-1/road.jpg" },
    { status: "uploaded" },
    { job_id: "job-1" },
  ];
  vi.stubGlobal("fetch", vi.fn(async (input: URL, init: RequestInit) => {
    calls.push({ url: input.toString(), init });
    const body = responses.shift();
    return { ok: true, json: async () => body };
  }));
  const file = new File(["real bytes"], "road.jpg", { type: "image/jpeg" });
  expect(await startAssessment(file)).toBe("job-1");
  expect(calls.map(({ url }) => new URL(url).pathname)).toEqual([
    "/v1/uploads", "/v1/uploads/upload-1/local", "/v1/uploads/upload-1/finalize",
  ]);
  expect(calls[1].init.body).toBe(file);
  expect(JSON.parse(String(calls[2].init.body))).toEqual({ source_mode: "upload", metadata: { source_mode: "upload" } });
});

test("a failed byte transfer never finalizes an upload", async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ upload_id: "upload-2", upload_url: "/v1/uploads/upload-2/local" }) })
    .mockResolvedValueOnce({ ok: false, status: 500 });
  vi.stubGlobal("fetch", fetcher);
  await expect(startAssessment(new File(["bytes"], "road.png", { type: "image/png" })))
    .rejects.toThrow("Image upload failed (500)");
  expect(fetcher).toHaveBeenCalledTimes(2);
});
