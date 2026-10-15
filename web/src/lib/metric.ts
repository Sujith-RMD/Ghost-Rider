/** UI-only presentation boundary. Replace adapter with published OpenAPI types. */
export type Metric =
  | {
      kind: "measured";
      value: number;
      unit: string;
      validity: "valid" | "limited";
      reason?: string;
      n?: number;
      lowerLimit?: number;
    }
  | { kind: "unknown"; reason: string }
  | { kind: "unsupported"; reason: string }
  | { kind: "uncalibrated"; pixelValue: number; unit: "px" };
export const measured = (value: number, unit = ""): Metric => ({
  kind: "measured",
  value,
  unit,
  validity: "valid",
});
export const unknown = (reason: string): Metric => ({
  kind: "unknown",
  reason,
});
export const unsupported = (reason: string): Metric => ({
  kind: "unsupported",
  reason,
});
export const numeric = (m: Metric): number | undefined =>
  m.kind === "measured" && Number.isFinite(m.value) ? m.value : undefined;
export const formatNumber = (value: number) =>
  new Intl.NumberFormat("en-IN", { maximumSignificantDigits: 4 }).format(value);
