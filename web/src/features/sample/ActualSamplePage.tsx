import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiBase, readSample, type ActualSample } from "../../api/real-assessment";
import { Card } from "../../components/primitives";
import { DistressDetectionOverlay } from "../../components/DistressDetectionOverlay";

export default function ActualSamplePage({ id }: { id: string }) {
  const [sample, setSample] = useState<ActualSample | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) { setError("Sample ID is missing."); return; }
    let active = true;
    readSample(id).then(
      (result) => { if (active) setSample(result); },
      (cause) => { if (active) setError(cause instanceof Error ? cause.message : "Could not load sample."); },
    );
    return () => { active = false; };
  }, [id]);

  return (
    <div className="content-page">
      <div className="page-heading"><div><h1>Sample evidence</h1><p>Stored result from the analysis service.</p></div></div>
      <Card title="Assessment result">
        {error ? <p role="alert">{error}</p> : !sample ? <p>Loading stored sample…</p> : (
          <div className="actual-result">
            {sample.image_url && <DistressDetectionOverlay imageUrl={new URL(sample.image_url, apiBase).toString()} evidence={sample.distress_detection} />}
            <p>Image quality: {sample.quality?.status ?? "Unavailable"}</p>
            {!!sample.quality?.reasons?.length && <p>Quality reasons: {sample.quality.reasons.join(", ")}</p>}
            <p>Road score: {sample.score?.value == null ? "Unavailable — scoring has not been validated" : `${sample.score.value} / 100 (${sample.score.status})`}</p>
            <p>Physical scale: {sample.geometry_valid ? "Validated" : "Uncalibrated; physical units unavailable"}</p>
            <p>Exploratory visible instance count: {sample.metrics?.chip_count ?? "Unavailable"}</p>
            <p>Count per m²: {sample.metrics?.chip_density_per_m2 ?? "Unavailable without calibrated area"}</p>
            {sample.error && <p>Analysis limitation: {sample.error}</p>}
            <p>Model: {sample.model_version ?? "Unavailable"}</p>
          </div>
        )}
        <Link className="button secondary" to="/assess">Back to assessment</Link>
        {sample?.sample_id && <Link className="button secondary" to={`/reports?sample=${encodeURIComponent(sample.sample_id)}`}>Generate report</Link>}
      </Card>
    </div>
  );
}
