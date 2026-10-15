import type { Metric } from "../lib/metric";
// Presentation models only. These are NOT a published backend contract.
export type Condition = "good" | "bad" | "review" | "unknown";
export type SourceMode = "live" | "replay" | "still";
export type Quality = "accepted" | "limited" | "rejected";
export type JobState =
  | "received"
  | "validated"
  | "queued"
  | "processing"
  | "succeeded"
  | "partial"
  | "failed";
export interface Layer {
  id: string;
  name: string;
  url?: string;
  reason?: string;
  pattern: "outline" | "stripe" | "dots";
  area: Metric;
  denominator: string;
}
export interface Sample {
  id: string;
  mode: SourceMode;
  quality: Quality;
  condition: Condition;
  score: Metric;
  scoreStatus: "provisional" | "calibrated";
  severe: boolean;
  reasons: string[];
  capturedAt: string | null;
  calibrated: boolean;
  gpsAccuracy: Metric;
  image?: string;
  schematic: boolean;
  width: number;
  height: number;
  scale: Metric;
  layers: Layer[];
  metrics: Record<
    string,
    { label: string; value: Metric; group: string; reference?: string }
  >;
  confidence: { name: string; state: string }[];
  versions: { name: string; value: string }[];
}
export interface Bin {
  id: string;
  start: Metric;
  end: Metric;
  accepted: Metric;
  area: Metric;
  median: Metric;
  lower: Metric;
  coverage: Metric;
  sampled: boolean;
  condition: Condition;
  severe: boolean;
  mode: SourceMode;
  geometry?: google.maps.LatLngLiteral[];
}
export interface Session {
  id: string;
  name: string;
  mode: SourceMode;
  simulated: boolean;
  hasGps: boolean;
  length: Metric;
  sampledLength: Metric;
  coverage: Metric;
  median: Metric;
  scoreStatus: "provisional" | "calibrated";
  bins: Bin[];
  samples: Sample[];
  threshold?: { value: Metric; label: string };
}
export interface Monitor {
  mode: "live" | "replay";
  connection: string;
  camera: string;
  stale: boolean;
  age: string;
  capturedAt: string | null;
  processedAt: string | null;
  counts: { label: string; metric: Metric }[];
}
export interface Report {
  id: string;
  sessionId: string;
  version: string;
  createdAt: string | null;
  mode: SourceMode;
  facts: { label: string; metric: Metric }[];
  narrative: string;
  fallback: boolean;
  modelId?: string;
  references: { id: string; label: string; href?: string }[];
  limitations: string[];
  actions: string[];
  exportUrl?: string;
}
export interface Health {
  name: string;
  state: "ready" | "degraded" | "unavailable";
  detail: string;
  checkedAt: string | null;
}
export interface Workspace {
  session: Session;
  monitor: Monitor;
  report: Report;
  health: Health[];
}
export interface DataSource {
  mock: boolean;
  contractVersion: string | null;
  load: () => Promise<Workspace>;
}
