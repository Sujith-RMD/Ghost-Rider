/** Phase 1 still-image slice against docs/contracts/openapi.v1.json (1.0.0). */
import type { components } from "../contract/generated";
export const apiBase = import.meta.env.VITE_API_BASE_URL || window.location.origin;

type UploadSlot = components["schemas"]["UploadResponse"];
export type Job = components["schemas"]["JobState"];
export type ActualSample = components["schemas"]["SegmentResult"];
export type ActualHealth = components["schemas"]["HealthStatus"];
export type ActualSession = components["schemas"]["SessionState"];
export type ActualReport = components["schemas"]["ReportResult"];

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(new URL(path, apiBase), {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init?.headers },
    signal: init?.signal ?? AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    let detail = `Service returned ${response.status}`;
    try {
      const body = await response.json() as { detail?: { message?: string } | string };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.message) detail = body.detail.message;
    } catch { /* Keep the status if the response is not JSON. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function startAssessment(file: File): Promise<string> {
  const slot = await json<UploadSlot>("/v1/uploads", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_type: file.type, expected_size: file.size }),
  });
  const target = new URL(slot.upload_url, apiBase);
  const uploaded = await fetch(target, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
    signal: AbortSignal.timeout(60000),
  });
  if (!uploaded.ok) throw new Error(`Image upload failed (${uploaded.status}).`);
  const finalized = await json<components["schemas"]["FinalizeResponse"]>(`/v1/uploads/${encodeURIComponent(slot.upload_id)}/finalize`, {
    method: "POST",
    body: JSON.stringify({ source_mode: "upload", metadata: { source_mode: "upload" } }),
  });
  if (!finalized.job_id) throw new Error("The service did not return an analysis job.");
  return finalized.job_id;
}

export const readJob = (jobId: string) =>
  json<Job>(`/v1/jobs/${encodeURIComponent(jobId)}`);

export const readSample = (sampleId: string) =>
  json<ActualSample>(`/v1/samples/${encodeURIComponent(sampleId)}`);

export const readHealth = () => json<ActualHealth>("/v1/health");

export const createLiveSession = (camera: string, signal?: AbortSignal) =>
  json<ActualSession>("/v1/sessions", { method: "POST", body: JSON.stringify({ mode: "live", camera_id: camera }), signal });
export const readSession = (id: string, signal?: AbortSignal) =>
  json<ActualSession>(`/v1/sessions/${encodeURIComponent(id)}`, { signal });
export const finishSession = (id: string) =>
  json<ActualSession>(`/v1/sessions/${encodeURIComponent(id)}/finish`, { method: "POST" });
export function sendFrame(id: string, frame: Blob, capturedAt: string, signal?: AbortSignal) {
  const body = new FormData();
  body.append("frame", frame, "camera-frame.jpg");
  body.append("metadata", JSON.stringify({ captured_at: capturedAt, source_mode: "live" }));
  return json<ActualSession>(`/v1/sessions/${encodeURIComponent(id)}/frames`, { method: "POST", body, signal });
}
export const createReport = (id: string, includeNarrative: boolean) =>
  json<ActualReport>("/v1/reports", { method: "POST", body: JSON.stringify({ assessment_id: id, include_narrative: includeNarrative }), signal: AbortSignal.timeout(60000) });
export const readReport = (id: string) => json<ActualReport>(`/v1/reports/${encodeURIComponent(id)}`);
