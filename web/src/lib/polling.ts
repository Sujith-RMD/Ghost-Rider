import type { JobState } from "../api/display";
export function jobPollingInterval(
  state: JobState,
  startedAt: number,
  now: number,
  hidden: boolean,
): number | false {
  if (hidden || ["succeeded", "partial", "failed"].includes(state))
    return false;
  return now - startedAt > 30000 ? 3000 : 1000;
}
export function isStale(
  flag: boolean,
  processedAt: string | null,
  thresholdMs?: number,
  now = Date.now(),
): boolean {
  if (flag) return true;
  if (!processedAt || thresholdMs === undefined) return false;
  return now - Date.parse(processedAt) > thresholdMs;
}
