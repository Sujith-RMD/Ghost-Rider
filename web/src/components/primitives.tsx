import type { ReactNode } from "react";
import {
  ArrowUpRight,
  Check,
  Eye,
  HelpCircle,
  X,
  Image as ImageIcon,
  Radio,
  Rewind,
  Diamond,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Metric } from "../lib/metric";
import { formatNumber, numeric } from "../lib/metric";
import type {
  Condition,
  Quality,
  SourceMode,
  JobState,
  Sample,
} from "../api/display";

export function MetricValue({
  metric,
  hero = false,
}: {
  metric: Metric;
  hero?: boolean;
}) {
  if (metric.kind === "unknown")
    return (
      <span className="metric unknown">
        <span className={hero ? "hero-number" : ""}>—</span>
        <small>{metric.reason}</small>
      </span>
    );
  if (metric.kind === "unsupported")
    return (
      <span className="metric unsupported">
        <HelpCircle size={14} />
        {metric.reason}
      </span>
    );
  if (metric.kind === "uncalibrated")
    return (
      <span className="metric pixels">
        <span>
          {formatNumber(metric.pixelValue)} <span className="unit">px</span>
        </span>
        <small>Pixels only</small>
      </span>
    );
  if (!Number.isFinite(metric.value))
    return (
      <MetricValue
        metric={{ kind: "unknown", reason: "Invalid measurement" }}
        hero={hero}
      />
    );
  const [integer, decimal] = formatNumber(metric.value).split(".");
  return (
    <span className={`metric measured ${hero ? "hero-number" : ""}`}>
      <span>
        {integer}
        {decimal && <span className="decimal">.{decimal}</span>}
        {metric.unit && <span className="unit"> {metric.unit}</span>}
      </span>
      {metric.validity === "limited" && (
        <small title={metric.reason}>
          Limited{metric.reason ? `: ${metric.reason}` : ""}
        </small>
      )}
      {metric.n !== undefined && <small>{metric.n} valid measurements</small>}
      {metric.lowerLimit !== undefined && (
        <small>
          Lower reporting limit: {metric.lowerLimit} {metric.unit}
        </small>
      )}
    </span>
  );
}
export const HeroNumber = ({ metric }: { metric: Metric }) => (
  <MetricValue metric={metric} hero />
);
const glyphs = { good: Check, bad: X, review: Eye, unknown: HelpCircle };
export function ConditionChip({
  condition,
  score,
}: {
  condition: Condition;
  score?: Metric;
}) {
  const actual = score && numeric(score) === undefined ? "unknown" : condition;
  const Glyph = glyphs[actual];
  return (
    <span className={`chip condition ${actual}`} data-condition={actual}>
      <Glyph size={13} />
      {actual === "good"
        ? "Good"
        : actual === "bad"
          ? "Bad"
          : actual === "review"
            ? "Review"
            : "Unknown"}
    </span>
  );
}
export function QualityChip({ quality }: { quality: Quality }) {
  const Glyph =
    quality === "accepted" ? Check : quality === "limited" ? Eye : X;
  return (
    <span className={`chip ${quality}`}>
      <Glyph size={13} />
      {quality[0].toUpperCase() + quality.slice(1)}
    </span>
  );
}
export function SourceModeChip({ mode }: { mode: SourceMode }) {
  const Glyph =
    mode === "live" ? Radio : mode === "replay" ? Rewind : ImageIcon;
  return (
    <span className={`chip source ${mode}`} data-mode={mode}>
      <Glyph size={13} />
      {mode[0].toUpperCase() + mode.slice(1)}
    </span>
  );
}
export const SevereDefectFlag = () => (
  <span className="severe">
    <Diamond size={14} />
    Inspect
  </span>
);
export function ScoreLabel({
  status,
}: {
  status: "provisional" | "calibrated";
}) {
  return (
    <span
      className="score-label"
      title={
        status === "provisional"
          ? "This reference comparison is not yet calibrated to human ratings."
          : undefined
      }
    >
      {status === "provisional"
        ? "Provisional reference-deviation index"
        : "Calibrated visual condition index"}
    </span>
  );
}
export function Card({
  title,
  href,
  children,
  className = "",
  glass = false,
}: {
  title?: string;
  href?: string;
  children: ReactNode;
  className?: string;
  glass?: boolean;
}) {
  return (
    <section className={`${glass ? "glass-card" : "card"} ${className}`}>
      {title && (
        <div className="card-heading">
          <h2>{title}</h2>
          {href && (
            <Link
              className="icon-button"
              to={href}
              aria-label={`Open ${title}`}
            >
              <ArrowUpRight size={18} />
            </Link>
          )}
        </div>
      )}
      {children}
    </section>
  );
}
export const GlassCard = (props: Omit<Parameters<typeof Card>[0], "glass">) => (
  <Card {...props} glass />
);
export function ErrorPanel({
  family,
  title,
  children,
  retry,
  code,
}: {
  family: "validation" | "analysis" | "integration";
  title: string;
  children?: ReactNode;
  retry?: () => void;
  code?: string;
}) {
  const [copied, setCopied] = ReactUseState(false);
  return (
    <div
      role="alert"
      className={`error-panel ${family}`}
      data-error-family={family}
    >
      <AlertTriangle size={19} />
      <div>
        <span className="error-family">
          {family[0].toUpperCase() + family.slice(1)}
        </span>
        <h3>{title}</h3>
        {children && <div className="error-copy">{children}</div>}
        <div className="actions">
          {retry && (
            <button className="button secondary" onClick={retry}>
              <RefreshCw size={15} />
              Retry
            </button>
          )}
          {code && (
            <button
              className="text-button"
              onClick={() => {
                void navigator.clipboard
                  ?.writeText(code)
                  .then(() => setCopied(true));
              }}
            >
              {copied ? "Diagnostic copied" : "Copy diagnostic"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
import { useState as ReactUseState } from "react";
export function JobStepper({
  state,
  reason,
}: {
  state: JobState;
  reason?: string;
}) {
  const sequence = [
    "received",
    "validated",
    "queued",
    "processing",
    "succeeded",
  ];
  const index =
    state === "partial" || state === "failed" ? 4 : sequence.indexOf(state);
  return (
    <div className={`job-stepper ${state}`} aria-live="polite">
      <ol>
        {sequence.map((step, i) => (
          <li
            key={step}
            className={i < index ? "complete" : i === index ? "current" : ""}
          >
            <span className="step-dot" />
            {i === 4
              ? state === "partial"
                ? "Partial result"
                : state === "failed"
                  ? "Failed"
                  : "Succeeded"
              : step[0].toUpperCase() + step.slice(1)}
          </li>
        ))}
      </ol>
      <p>
        {state === "queued"
          ? "Uploaded. Analysis hasn't finished yet."
          : state === "partial"
            ? "Partial result. Some measurements are unavailable."
            : state === "failed"
              ? "Analysis failed."
              : state === "succeeded"
                ? "Analysis succeeded."
                : `Analysis stage: ${state}.`}
      </p>
      {reason && <p>{reason}</p>}
    </div>
  );
}
export const StaleBadge = ({ age }: { age: string }) => (
  <div className="stale-badge" role="status">
    <HelpCircle size={16} />
    <span>Stale result. Last processed {age} ago.</span>
  </div>
);
export function SampleCard({ sample }: { sample: Sample }) {
  return (
    <Link
      to={`/samples/${sample.id}`}
      className="sample-card"
      aria-label={`Open ${sample.id}, ${sample.mode}, ${sample.quality}`}
    >
      <div className="sample-image">
        {sample.image ? (
          <img
            src={sample.schematic ? "/fixtures/road-placeholder.png" : sample.image}
            alt={
              sample.schematic
                ? "Placeholder road-texture illustration, not captured evidence"
                : "Original captured road surface"
            }
            loading="lazy"
          />
        ) : (
          <span>No image supplied</span>
        )}
      </div>
      <div className="sample-topline">
        <div className="chip-row">
          <SourceModeChip mode={sample.mode} />
          <QualityChip quality={sample.quality} />
        </div>
        <ArrowUpRight size={16} />
      </div>
      <div className="sample-body">
        <div className="sample-heading">
          <h3 title={sample.capturedAt ?? "Capture time not supplied"}>
            {sample.capturedAt
              ? new Date(sample.capturedAt).toLocaleTimeString("en-IN", {
                  timeZone: "Asia/Kolkata",
                  hour12: false,
                })
              : "Time unknown"}
          </h3>
        </div>
        {sample.schematic && (
          <p className="sample-placeholder">Placeholder texture</p>
        )}
        <div className="sample-support">
          <span className="chip">
            {sample.gpsAccuracy.kind === "measured"
              ? `GPS ±${formatNumber(sample.gpsAccuracy.value)} m`
              : "No GPS"}
          </span>
          <span className="chip">
            {sample.calibrated ? "Calibrated fixture" : "Uncalibrated"}
          </span>
        </div>
        <div className="sample-verdict">
          <ConditionChip condition={sample.condition} score={sample.score} />
          {sample.severe && <SevereDefectFlag />}
        </div>
      </div>
    </Link>
  );
}
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <HelpCircle size={24} />
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}
