import { useParams } from "react-router-dom";
import type { Session } from "../../api/display";
import {
  Card,
  EmptyState,
  MetricValue,
  ScoreLabel,
  SourceModeChip,
} from "../../components/primitives";
import { RouteChart } from "../../components/RouteChart";
import { SegmentTable } from "../../components/SegmentTable";
export default function SessionPage({ session }: { session: Session }) {
  const { id } = useParams();
  if (id !== session.id)
    return (
      <EmptyState title="Session not found">
        Choose an available session.
      </EmptyState>
    );
  return (
    <div className="content-page">
      <div className="page-heading">
        <div>
          <h1>Session summary</h1>
          <p>{session.name}</p>
        </div>
        <SourceModeChip mode={session.mode} />
      </div>
      <div className="session-heroes">
        <div>
          <span>Sampled length</span>
          <MetricValue metric={session.sampledLength} hero />
          <small>
            of <MetricValue metric={session.length} />
          </small>
        </div>
        <div>
          <span>Route coverage</span>
          <MetricValue metric={session.coverage} hero />
          <small>Observed strip, not full-lane coverage</small>
        </div>
        <div>
          <MetricValue metric={session.median} hero />
          <ScoreLabel status={session.scoreStatus} />
        </div>
      </div>
      <Card title="Condition along route">
        <RouteChart session={session} />
      </Card>
      <Card title="Unknown and unsampled stretches">
        <ul className="plain-list">
          {session.bins
            .filter((b) => !b.sampled)
            .map((b) => (
              <li key={b.id}>
                <MetricValue metric={b.start} /> to{" "}
                <MetricValue metric={b.end} />: not sampled. We have no
                measurements for this stretch.
              </li>
            ))}
        </ul>
      </Card>
      <Card title="Segment evidence">
        <SegmentTable bins={session.bins} />
      </Card>
    </div>
  );
}
