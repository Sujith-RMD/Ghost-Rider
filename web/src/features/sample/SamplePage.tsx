import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { Session, Sample } from "../../api/display";
import {
  Card,
  ConditionChip,
  EmptyState,
  MetricValue,
  QualityChip,
  ScoreLabel,
  SevereDefectFlag,
  SourceModeChip,
} from "../../components/primitives";
import { EvidenceViewer } from "../../components/EvidenceViewer";
function MeasurementTabs({ sample }: { sample: Sample }) {
  const [tab, setTab] = useState("Surface");
  const tabs = [
    "Surface",
    "Distress",
    "Geometry",
    "Position",
    "Inclination",
    "Versions",
  ];
  return (
    <div className="measurement-tabs">
      <div className="tabs" role="tablist" aria-label="Measurements">
        {tabs.map((t) => (
          <button
            id={`tab-${t}`}
            role="tab"
            aria-controls="measurement-panel"
            aria-selected={t === tab}
            key={t}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                const i =
                  (tabs.indexOf(tab) +
                    (e.key === "ArrowRight" ? 1 : -1) +
                    tabs.length) %
                  tabs.length;
                setTab(tabs[i]);
                document.getElementById(`tab-${tabs[i]}`)?.focus();
              }
            }}
            tabIndex={t === tab ? 0 : -1}
          >
            {t}
          </button>
        ))}
      </div>
      <div
        id="measurement-panel"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
      >
        {tab === "Versions" ? (
          <dl>
            {sample.versions.map((v) => (
              <div key={v.name}>
                <dt>{v.name}</dt>
                <dd>{v.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <dl>
            {Object.entries(sample.metrics)
              .filter(([, v]) => v.group === tab)
              .map(([id, v]) => (
                <div key={id}>
                  <dt>{v.label}</dt>
                  <dd>
                    <MetricValue metric={v.value} />
                    {v.reference && <small>{v.reference}</small>}
                  </dd>
                </div>
              ))}
          </dl>
        )}
        {tab === "Position" && (
          <p className="muted">
            Capture time: {sample.capturedAt ?? "Not supplied"}. Coordinates and
            receive time not supplied by this fixture.
          </p>
        )}
        {tab === "Geometry" && (
          <p className="muted">
            Geometry validity and uncertainty await the ML contract.
          </p>
        )}
        {tab === "Distress" && (
          <p className="muted">
            Ravelling, bleeding and polishing require human review. No automated
            flag supplied.
          </p>
        )}
        {tab === "Inclination" && (
          <p className="muted">
            Requires a verified supporting measurement with source, capture time
            and uncertainty.
          </p>
        )}
      </div>
    </div>
  );
}
export default function SamplePage({ session }: { session: Session }) {
  const { id } = useParams();
  const sample = session.samples.find((s) => s.id === id);
  if (!sample)
    return (
      <EmptyState title="Sample not found">
        Choose a sample from the Samples page.
      </EmptyState>
    );
  return (
    <div className="content-page sample-page">
      <div className="page-heading">
        <div>
          <Link className="back-link" to="/samples">
            ← Samples
          </Link>
          <h1>Sample {sample.id.replace("sample-", "")}</h1>
        </div>
        <div className="chip-row">
          <SourceModeChip mode={sample.mode} />
          <QualityChip quality={sample.quality} />
          <span className="chip">
            {sample.calibrated ? "Calibrated fixture" : "Uncalibrated"}
          </span>
        </div>
      </div>
      {sample.quality === "rejected" && (
        <div role="alert" className="rejection-banner">
          {sample.reasons[0]}
        </div>
      )}
      <div className="evidence-layout">
        <EvidenceViewer key={sample.id} sample={sample} />
        <div className="assessment-column">
          <Card title="Surface assessment">
            <MetricValue metric={sample.score} hero />
            <ScoreLabel status={sample.scoreStatus} />
            <div className="chip-row">
              <ConditionChip
                condition={sample.condition}
                score={sample.score}
              />
              {sample.severe && <SevereDefectFlag />}
            </div>
            <div className="reason-list">
              {sample.reasons.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </div>
          </Card>
          {sample.quality !== "rejected" && (
            <>
              <MeasurementTabs sample={sample} />
              <Card title="Trust and support">
                <dl>
                  {sample.confidence.map((c) => (
                    <div key={c.name}>
                      <dt>{c.name}</dt>
                      <dd>{c.state}</dd>
                    </div>
                  ))}
                </dl>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
