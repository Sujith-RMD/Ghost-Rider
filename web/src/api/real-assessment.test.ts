import { afterEach, expect, test, vi } from "vitest";
import { startAssessment, sendFrame, createReport } from "./real-assessment";

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

test("live frames use multipart bytes and real capture metadata", async () => {
  const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({ session_id: "session-1" }) }));
  vi.stubGlobal("fetch", fetcher);
  await sendFrame("session-1", new Blob(["camera bytes"], { type: "image/jpeg" }), "2026-10-16T06:00:00Z");
  const init = (fetcher.mock.calls as unknown as [URL, RequestInit][])[0][1];
  expect(init.headers).not.toHaveProperty("Content-Type");
  expect((init.body as FormData).get("frame")).toBeInstanceOf(File);
  expect(JSON.parse(String((init.body as FormData).get("metadata")))).toEqual({ captured_at: "2026-10-16T06:00:00Z", source_mode: "live" });
});

test("reports send only an assessment reference and narrative choice", async () => {
  const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({ report_id: "r1" }) }));
  vi.stubGlobal("fetch", fetcher);
  await createReport("stored-sample", false);
  const init = (fetcher.mock.calls as unknown as [URL, RequestInit][])[0][1];
  expect(JSON.parse(String(init.body))).toEqual({ assessment_id: "stored-sample", include_narrative: false });
});
