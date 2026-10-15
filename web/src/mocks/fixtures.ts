// MOCK: replace with the published contract
import type { DataSource, Sample, Bin, Workspace } from "../api/display";
import { measured as m, unknown as u, unsupported as x } from "../lib/metric";
const base: Sample = {
  id: "sample-01",
  mode: "still",
  quality: "accepted",
  condition: "review",
  score: m(58.2),
  scoreStatus: "provisional",
  severe: true,
  reasons: [
    "Gap variation is higher than the reviewed reference.",
    "Possible crack footprint needs human inspection.",
  ],
  capturedAt: "2026-10-15T10:14:32Z",
  calibrated: true,
  gpsAccuracy: u("No GPS fix"),
  image: "/fixtures/surface.svg",
  schematic: true,
  width: 960,
  height: 640,
  scale: m(0.91, "mm/px"),
  layers: [
    {
      id: "aggregate",
      name: "Aggregate instances",
      url: "/fixtures/aggregate.svg",
      pattern: "outline",
      area: m(0.31, "m²"),
      denominator: "Eligible texture area",
    },
    {
      id: "crack",
      name: "Crack mask",
      url: "/fixtures/crack.svg",
      pattern: "stripe",
      area: m(0.006, "m²"),
      denominator: "Observed road area",
    },
    {
      id: "road",
      name: "Rectified road area",
      reason: "No rectification image supplied",
      pattern: "dots",
      area: u("Not supplied"),
      denominator: "Observed road area",
    },
  ],
  metrics: {
    count: {
      label: "Visible chips (2D exposed appearance)",
      value: m(384, "chips"),
      group: "Surface",
    },
    density: {
      label: "Count density",
      value: m(960, "chips/m²"),
      group: "Surface",
      reference: "Reference 910 chips/m²; higher than reference",
    },
    eligible: {
      label: "Eligible texture area",
      value: m(0.4, "m²"),
      group: "Surface",
    },
    diameter: {
      label: "Median equivalent diameter",
      value: m(8.4, "mm"),
      group: "Surface",
    },
    minimum: {
      label: "Minimum measurable diameter",
      value: m(4, "mm"),
      group: "Surface",
    },
    gap: {
      label: "Median adjacent-boundary gap",
      value: {
        kind: "measured",
        value: 3.2,
        unit: "mm",
        validity: "limited",
        reason: "Near the lower reporting limit",
        n: 42,
        lowerLimit: 3,
      },
      group: "Surface",
      reference: "Reference 2.8 mm; higher than reference",
    },
    gapIqr: { label: "Gap IQR", value: m(1.1, "mm"), group: "Surface" },
    gapP90: { label: "Gap p90", value: m(4.8, "mm"), group: "Surface" },
    coverage: {
      label: "Aggregate union coverage",
      value: m(77.5, "%"),
      group: "Surface",
    },
    texture: {
      label: "Texture proxy",
      value: m(0.43, "unitless"),
      group: "Surface",
    },
    crack: {
      label: "Crack skeleton length",
      value: m(0.12, "m"),
      group: "Distress",
    },
    pothole: {
      label: "Pothole mask area",
      value: m(0, "m²"),
      group: "Distress",
    },
    observed: {
      label: "Observed road area",
      value: m(0.5, "m²"),
      group: "Geometry",
    },
    ignored: {
      label: "Ignored area",
      value: m(0.094, "m²"),
      group: "Geometry",
    },
    unique: {
      label: "Unique inspected area",
      value: u("Registration not verified"),
      group: "Geometry",
    },
    grade: {
      label: "Longitudinal grade",
      value: x("No verified grade for this sample"),
      group: "Inclination",
    },
    position: {
      label: "GPS accuracy",
      value: u("No GPS fix"),
      group: "Position",
    },
    distance: {
      label: "Route distance",
      value: m(150, "m"),
      group: "Position",
    },
  },
  confidence: [
    { name: "Image quality", state: "Accepted" },
    { name: "Scale", state: "Source calibrated (fixture)" },
    { name: "Reference support", state: "Provisional" },
    { name: "Indian transfer", state: "Not validated" },
  ],
  versions: [
    { name: "Model", value: "Fixture model only" },
    { name: "Reference", value: "Fixture reference only" },
    { name: "Score policy", value: "Fixture provisional policy" },
    { name: "Feature estimator", value: "Fixture feature version" },
  ],
};
export const samples: Sample[] = [
  base,
  {
    ...base,
    id: "sample-02",
    mode: "replay",
    quality: "limited",
    condition: "unknown",
    score: u("Scale not calibrated"),
    calibrated: false,
    severe: false,
    reasons: ["Scale not calibrated. Measurements are in pixels only."],
    scale: { kind: "uncalibrated", pixelValue: 1, unit: "px" },
    metrics: {
      diameter: {
        label: "Median equivalent diameter",
        value: { kind: "uncalibrated", pixelValue: 9.2, unit: "px" },
        group: "Surface",
      },
      grade: base.metrics.grade,
    },
    layers: [],
    capturedAt: "2026-10-15T10:14:26Z",
  },
  {
    ...base,
    id: "sample-03",
    mode: "live",
    condition: "good",
    severe: false,
    score: m(82.1),
    reasons: ["Fixture appearance is close to the reviewed reference."],
    capturedAt: "2026-10-15T10:14:20Z",
  },
  {
    ...base,
    id: "sample-04",
    mode: "still",
    quality: "rejected",
    condition: "unknown",
    score: x("Image too blurred to measure"),
    severe: false,
    reasons: [
      "Rejected. The image is too blurred to measure. Try a slower pass or a faster shutter.",
    ],
    capturedAt: "2026-10-15T10:14:14Z",
  },
  {
    ...base,
    id: "sample-05",
    mode: "replay",
    condition: "bad",
    score: m(32.7),
    reasons: ["Fixture distress burden is elevated."],
    capturedAt: "2026-10-15T10:14:08Z",
  },
];
const values = [
  82.1,
  79.3,
  75.4,
  null,
  null,
  58.2,
  62.4,
  68.1,
  72.6,
  69.2,
  32.7,
  49.8,
];
export const bins: Bin[] = values.map((v, i) => ({
  id: `bin-${i + 1}`,
  start: m(i * 50, "m"),
  end: m((i + 1) * 50, "m"),
  accepted: m(v === null ? 0 : i === 10 ? 2 : 4),
  area: v === null ? u("Not sampled") : m(1.2, "m²"),
  median: v === null ? u("Not sampled") : m(v),
  lower: v === null ? u("Not sampled") : m(v - 8),
  coverage: m(v === null ? 0 : 64, "%"),
  sampled: v !== null,
  condition:
    v === null ? "unknown" : i === 10 ? "bad" : i < 3 ? "good" : "review",
  severe: i === 10,
  mode: "replay",
}));
export const workspace: Workspace = {
  session: {
    id: "session-demo",
    name: "Indian-road inspection / interface fixture",
    mode: "replay",
    simulated: true,
    hasGps: false,
    length: m(600, "m"),
    sampledLength: m(500, "m"),
    coverage: m(83.3, "%"),
    median: m(68.1),
    scoreStatus: "provisional",
    bins,
    samples,
  },
  monitor: {
    mode: "replay",
    connection: "Recorded fixture",
    camera: "No live camera connected",
    stale: true,
    age: "14 s (fixture)",
    capturedAt: "2026-10-15T10:14:32Z",
    processedAt: "2026-10-15T10:14:34Z",
    counts: [
      { label: "Received", metric: m(42) },
      { label: "Processed", metric: m(32) },
      { label: "Rejected", metric: m(6) },
      { label: "Dropped", metric: m(4) },
    ],
  },
  report: {
    id: "report-demo",
    sessionId: "session-demo",
    version: "Fixture v1",
    createdAt: "2026-10-15T10:16:00Z",
    mode: "replay",
    facts: [
      { label: "Sampled length", metric: m(500, "m") },
      { label: "Total route length", metric: m(600, "m") },
      { label: "Coverage", metric: m(83.3, "%") },
      { label: "Provisional reference-deviation index", metric: m(68.1) },
      {
        label: "Verified grade",
        metric: x("No verified grade for this sample"),
      },
    ],
    narrative:
      "The sampled strip includes a possible crack footprint that requires inspection. Unsampled stretches have no condition assessment. This is an interface fixture, not a road-quality finding.",
    fallback: true,
    references: [
      { id: "sample-01", label: "Sample 01", href: "/samples/sample-01" },
      { id: "missing", label: "Missing evidence" },
    ],
    limitations: [
      "All values and evidence in this preview are synthetic fixtures.",
      "Actual live capture and Indian-domain transfer have not been validated.",
      "No verified physical inclination or unique-area registration is available.",
    ],
    actions: [
      "Compare the original image and masks before deciding.",
      "Obtain calibrated live-camera evidence and inspect unsampled stretches.",
    ],
  },
  health: [
    {
      name: "Model",
      state: "unavailable",
      detail: "No validated model connected",
      checkedAt: null,
    },
    {
      name: "Worker",
      state: "unavailable",
      detail: "Backend contract pending",
      checkedAt: null,
    },
    {
      name: "Storage",
      state: "unavailable",
      detail: "Private upload integration pending",
      checkedAt: null,
    },
    {
      name: "Bedrock",
      state: "unavailable",
      detail: "Template fixture only; no Bedrock call made",
      checkedAt: null,
    },
  ],
};
// Simulated GPS is independent of the schematic sample thumbnails; no real capture is claimed.
const routeNodes = Array.from({ length: 13 }, (_, i) => ({
  lat: 12.9716 + i * 0.00035,
  lng: 77.5946 + Math.sin(i * 0.32) * 0.0012 + i * 0.00012,
}));
export const simulatedWorkspace: Workspace = {
  ...workspace,
  session: {
    ...workspace.session,
    name: "Simulated inspection preview",
    hasGps: true,
    simulated: true,
    bins: workspace.session.bins.map((bin, i) => ({
      ...bin,
      geometry: [routeNodes[i], routeNodes[i + 1]],
    })),
  },
};
export const dataSource: DataSource = {
  mock: true,
  contractVersion: null,
  load: async () =>
    new URLSearchParams(window.location.search).get("fixture") === "no-gps"
      ? workspace
      : simulatedWorkspace,
};
