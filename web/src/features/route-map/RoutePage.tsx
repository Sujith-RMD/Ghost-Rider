import { lazy, Suspense, useState } from "react";
import {
  ChevronDown,
  MapPinOff,
  Layers,
  ArrowUpRight,
  Check,
  Eye,
  X,
  Navigation,
  ScanLine,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Session, SourceMode, Quality } from "../../api/display";
import { measured, numeric } from "../../lib/metric";
import {
  Card,
  GlassCard,
  MetricValue,
  ScoreLabel,
  SampleCard,
  ConditionChip,
  SourceModeChip,
  SevereDefectFlag,
  EmptyState,
} from "../../components/primitives";
import { AbstractBackdrop } from "../../components/AbstractBackdrop";
import { RouteChart } from "../../components/RouteChart";
import { SegmentTable } from "../../components/SegmentTable";
import { useSelection } from "../../app/store";
const GoogleRouteMap = lazy(() => import("./GoogleRouteMap"));
export function DistanceStrip({ session }: { session: Session }) {
  const select = useSelection((s) => s.selectBin);
  const selected = useSelection((s) => s.binId);
  return (
    <div className="distance-report">
      <div className="distance-heading">
        <span>Linear distance report</span>
        <span>50 m reporting bins</span>
      </div>
      <div className="distance-bins">
        {session.bins.map((b, i) => (
          <button
            key={b.id}
            style={{ animationDelay: `${i * 60}ms` }}
            className={`distance-bin ${b.sampled ? (numeric(b.median) === undefined ? "unknown" : b.condition) : "unsampled"} ${selected === b.id ? "selected" : ""}`}
            onClick={() => select(b.id)}
            aria-label={`${b.id}: ${b.sampled ? (numeric(b.median) === undefined ? "unknown" : b.condition) : "not sampled"}`}
            aria-pressed={selected === b.id}
            title={
              b.sampled
                ? `Sampled strip: ${b.condition}`
                : "Not sampled. No condition claim."
            }
          >
            <span>{b.id.replace("bin-", "")}</span>
          </button>
        ))}
      </div>
      <div className="distance-labels">
        <span>0 m</span>
        <MetricValue metric={session.length} />
      </div>
      <div className="condition-legend">
        <ConditionChip condition="good" />
        <ConditionChip condition="bad" />
        <ConditionChip condition="review" />
        <span className="legend-unsampled">Not sampled</span>
      </div>
    </div>
  );
}
export default function RoutePage({ session }: { session: Session }) {
  const [mapFailure, setMapFailure] = useState<string | null>(null);
  const [mapAnchor, setMapAnchor] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [mode, setMode] = useState<"all" | SourceMode>("all");
  const [quality, setQuality] = useState<Quality | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [layerMenu, setLayerMenu] = useState(false);
  const selected = useSelection((s) => s.binId);
  const select = useSelection((s) => s.selectBin);
  const bin = session.bins.find((b) => b.id === selected);
  const filtered = session.samples.filter(
    (s) =>
      (mode === "all" || s.mode === mode) &&
      (!quality || s.quality === quality),
  );
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  const usableMap = session.hasGps && Boolean(key) && !mapFailure;
  return (
    <div className="route-layout refined-route">
      <aside
        className="route-sidebar"
        aria-label="Route evidence"
        onScroll={(e) =>
          document
            .querySelector(".app-header")
            ?.classList.toggle("rail-scrolled", e.currentTarget.scrollTop > 8)
        }
      >
        <div className="source-filters">
          {(["all", "live", "replay", "still"] as const).map((item) => (
            <button
              key={item}
              aria-pressed={item === mode}
              onClick={() => setMode(item)}
            >
              <span>{item[0].toUpperCase() + item.slice(1)}</span>
              <MetricValue
                metric={measured(
                  session.samples.filter(
                    (s) => item === "all" || s.mode === item,
                  ).length,
                )}
              />
            </button>
          ))}
        </div>
        <Card title="Image quality" className="quality-card">
          <div className="quality-tiles">
            {(["accepted", "limited", "rejected"] as const).map((q) => (
              <button
                className={`quality-tile ${q}`}
                key={q}
                aria-pressed={quality === q}
                onClick={() => setQuality(quality === q ? null : q)}
              >
                <span className="quality-glyph">
                  {q === "accepted" ? (
                    <Check size={15} />
                  ) : q === "limited" ? (
                    <Eye size={15} />
                  ) : (
                    <X size={15} />
                  )}
                </span>
                <span className="quality-name">
                  {q[0].toUpperCase() + q.slice(1)}
                </span>
                <MetricValue
                  metric={measured(
                    session.samples.filter((s) => s.quality === q).length,
                  )}
                  hero
                />
              </button>
            ))}
          </div>
        </Card>
        <Card
          title="Condition along route"
          className="condition-card"
          href={`/sessions/${session.id}`}
        >
          <RouteChart session={session} compact />
          <div className="chart-coverage">
            <span>Coverage</span>
            <MetricValue metric={session.coverage} />
          </div>
        </Card>
        <div className="section-heading">
          <h2>Recent samples</h2>
          <span>{filtered.length} shown</span>
        </div>
        <div className="sample-grid">
          {filtered.map((s) => (
            <SampleCard key={s.id} sample={s} />
          ))}
        </div>
        {!filtered.length && (
          <EmptyState title="No matching samples">
            Choose another source or image-quality filter.
          </EmptyState>
        )}
      </aside>
      <section className="route-stage" aria-label="Route condition">
        <AbstractBackdrop />
        {usableMap && (
          <Suspense fallback={null}>
            <GoogleRouteMap
              session={session}
              onUnavailable={setMapFailure}
              onAnchor={setMapAnchor}
            />
          </Suspense>
        )}
        <div className="stage-heading">
          <h1>Route condition</h1>
          <p>Observed evidence. Visible limits.</p>
          <div className="map-toolbar">
            <details className="session-menu">
              <summary className="glass-pill">
                <Navigation size={15} />
                {session.simulated ? "Inspection preview" : session.name}
                <ChevronDown size={14} />
              </summary>
              <div className="session-options card">
                <span>Interface fixtures</span>
                <a
                  href="/?fixture=simulated"
                  aria-current={session.hasGps ? "true" : undefined}
                >
                  Simulated GPS session
                  <small>Illustrative coordinates only</small>
                </a>
                <a
                  href="/?fixture=no-gps"
                  aria-current={!session.hasGps ? "true" : undefined}
                >
                  No-GPS session<small>Linear distance report only</small>
                </a>
              </div>
            </details>
            <button
              className="glass-pill"
              onClick={() => setLayerMenu(!layerMenu)}
              aria-expanded={layerMenu}
            >
              <Layers size={15} />
              Layers
              <ChevronDown size={14} />
            </button>
            <SourceModeChip mode={session.mode} />
          </div>
        </div>
        <div className="map-provenance">
          {session.simulated && session.hasGps && (
            <span className="chip simulated-route-label">
              <Navigation size={13} />
              Simulated route
            </span>
          )}
          {!usableMap && (
            <span className="chip abstract-label">
              <ScanLine size={13} />
              Abstract backdrop, not a map
            </span>
          )}
        </div>
        {!usableMap && (
          <div className="map-status">
            <MapPinOff size={19} />
            <div>
              <h2>Map unavailable</h2>
              <p>
                {session.hasGps
                  ? "Google Maps is unavailable. Showing the distance report."
                  : "This session has no GPS fix, so condition is shown by distance only."}
              </p>
              {session.hasGps && (
                <span
                  className="map-integration-note"
                  data-error-family="integration"
                >
                  Google Maps integration / {mapFailure ?? "key required"}
                </span>
              )}
            </div>
          </div>
        )}
        {layerMenu && (
          <div className="layer-menu glass-card">
            <label>
              <input
                type="checkbox"
                checked={useSelection.getState().layers.bins}
                onChange={() => useSelection.getState().toggleLayer("bins")}
              />
              Route bins
            </label>
            <p>
              Raw GPS points and accuracy circles await verified per-point
              records.
            </p>
          </div>
        )}
        <div className="coverage-float">
          <GlassCard title="Route coverage" href={`/sessions/${session.id}`}>
            <MetricValue metric={session.coverage} hero />
            <p className="coverage-detail">
              <MetricValue metric={session.sampledLength} /> of{" "}
              <MetricValue metric={session.length} />
              <span>Length coverage, not full-lane area</span>
            </p>
            <div className="coverage-note">
              <i />
              Observed strip only
            </div>
          </GlassCard>
        </div>
        <div className="distance-float">
          <GlassCard>
            <DistanceStrip session={session} />
            <p className="distance-disclaimer">
              {session.simulated ? "Illustrative session. " : " "}Unsampled
              stretches carry no condition assessment.
            </p>
          </GlassCard>
        </div>
        {bin && (
          <div
            className="selected-bin glass-card"
            style={
              usableMap && mapAnchor
                ? {
                    left: Math.max(24, mapAnchor.x - 165),
                    top: Math.max(290, mapAnchor.y - 160),
                  }
                : undefined
            }
          >
            <button
              className="close-button"
              aria-label="Close selected bin"
              onClick={() => select(null)}
            >
              <X size={17} />
            </button>
            <div className="selected-bin-heading">
              <h2>{bin.id}</h2>
              <SourceModeChip mode={bin.mode} />
            </div>
            <p>
              <MetricValue metric={bin.start} /> to{" "}
              <MetricValue metric={bin.end} />
            </p>
            <MetricValue metric={bin.median} hero />
            <ScoreLabel status={session.scoreStatus} />
            <div className="chip-row">
              {bin.sampled ? (
                <ConditionChip condition={bin.condition} score={bin.median} />
              ) : (
                <span>Not sampled</span>
              )}
              {bin.severe && <SevereDefectFlag />}
            </div>
            <dl>
              <div>
                <dt>Accepted samples</dt>
                <dd>
                  <MetricValue metric={bin.accepted} />
                </dd>
              </div>
              <div>
                <dt>Strip area</dt>
                <dd>
                  <MetricValue metric={bin.area} />
                </dd>
              </div>
              <div>
                <dt>Lower-tail index</dt>
                <dd>
                  <MetricValue metric={bin.lower} />
                </dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>
                  <MetricValue metric={bin.coverage} />
                </dd>
              </div>
            </dl>
            <Link to={`/sessions/${session.id}`} className="text-button">
              Open session
              <ArrowUpRight size={15} />
            </Link>
          </div>
        )}
        <div className={`segment-drawer ${expanded ? "expanded" : ""}`}>
          <button
            className="drawer-toggle"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            <span>
              Segment evidence
              <small>{session.bins.length} reporting bins</small>
            </span>
            <ChevronDown size={18} />
          </button>
          {expanded && <SegmentTable bins={session.bins} />}
        </div>
      </section>
    </div>
  );
}
