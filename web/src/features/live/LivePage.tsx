import { formatTimestamp } from "../../lib/format";
import { useState } from "react";
import { Radio, Rewind } from "lucide-react";
import { Link } from "react-router-dom";
import type { Monitor, Session } from "../../api/display";
import {
  Card,
  MetricValue,
  SourceModeChip,
  StaleBadge,
  SampleCard,
} from "../../components/primitives";
import { DistanceStrip } from "../route-map/RoutePage";
export function LiveMonitor({ monitor }: { monitor: Monitor }) {
  return (
    <div className={`live-monitor ${monitor.stale ? "stale" : ""}`}>
      <div className={`monitor-banner ${monitor.mode}`}>
        <SourceModeChip mode={monitor.mode} />
        <span>
          {monitor.mode === "replay"
            ? "Replay. This is a recorded file, not a live camera."
            : "Live-camera mode. Verify the connection state below."}
        </span>
      </div>
      {monitor.stale && <StaleBadge age={monitor.age} />}
      <dl>
        <div>
          <dt>Connection</dt>
          <dd>{monitor.connection}</dd>
        </div>
        <div>
          <dt>Camera</dt>
          <dd>{monitor.camera}</dd>
        </div>
        <div>
          <dt>Last capture</dt>
          <dd>
            <time
              dateTime={monitor.capturedAt ?? undefined}
              title={monitor.capturedAt ?? undefined}
            >
              {formatTimestamp(monitor.capturedAt)}
            </time>
          </dd>
        </div>
        <div>
          <dt>Last processed</dt>
          <dd>
            <time
              dateTime={monitor.processedAt ?? undefined}
              title={monitor.processedAt ?? undefined}
            >
              {formatTimestamp(monitor.processedAt)}
            </time>
          </dd>
        </div>
      </dl>
      <div className="monitor-counts">
        {monitor.counts.map((c) => (
          <div key={c.label}>
            <MetricValue metric={c.metric} hero />
            <span>{c.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
export default function LivePage({
  session,
  monitor,
}: {
  session: Session;
  monitor: Monitor;
}) {
  const [mode, setMode] = useState<"live" | "replay">("replay");
  return (
    <div className="content-page">
      <div className="page-heading">
        <div>
          <h1>Capture and inspect</h1>
          <p>Live access is a requirement. Connection evidence comes first.</p>
        </div>
      </div>
      <div className="two-columns live-columns">
        <div>
          <Card title="Start a session">
            <div className="mode-select">
              <button
                aria-pressed={mode === "live"}
                onClick={() => setMode("live")}
              >
                <Radio size={16} />
                Live camera
              </button>
              <button
                aria-pressed={mode === "replay"}
                onClick={() => setMode("replay")}
              >
                <Rewind size={16} />
                Replay recording
              </button>
            </div>
            <p>
              {mode === "replay"
                ? "Replay uses a recorded file. It tests the pipeline, not the camera."
                : "No live camera connected. Acquire and calibrate a supported device before starting."}
            </p>
            <dl>
              <div>
                <dt>Camera profile</dt>
                <dd>Not supplied</dd>
              </div>
              <div>
                <dt>Calibration ID</dt>
                <dd>Not supplied</dd>
              </div>
            </dl>
            <p className="muted">
              Measurements without calibration will be in pixels only.
            </p>
            <button className="button primary" disabled>
              Start {mode === "live" ? "live session" : "replay"}
            </button>
            <p className="muted">
              Session creation and transport await the published backend
              contract.
            </p>
          </Card>
          <Card title="Route evidence">
            <DistanceStrip session={session} />
            <Link to={`/sessions/${session.id}`} className="text-button">
              Open session summary
            </Link>
          </Card>
        </div>
        <div>
          <Card title="Session monitor">
            <LiveMonitor monitor={monitor} />
            <button className="button secondary" disabled>
              Finish session
            </button>
            <p className="muted">Preview only. No session is running.</p>
          </Card>
          <div className="section-heading">
            <h2>Latest fixture evidence</h2>
          </div>
          {session.samples[0] && (
            <div className="latest-sample">
              <SampleCard sample={session.samples[0]} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
