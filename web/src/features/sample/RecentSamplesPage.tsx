import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { readSample } from "../../api/real-assessment";
import { recentSampleIds } from "../../api/recent-samples";

export default function RecentSamplesPage() {
  const ids = recentSampleIds();
  const query = useQuery({
    queryKey: ["recent-samples", ids.join(",")],
    queryFn: () => Promise.allSettled(ids.map(readSample)),
    retry: false,
  });
  const samples = query.data?.flatMap((result) => result.status === "fulfilled" ? [result.value] : []) ?? [];
  return (
    <div className="content-page">
      <div className="page-heading"><div><h1>Recent samples</h1><p>Assessments completed in this browser. Each result is loaded from the assessment service.</p></div></div>
      {!ids.length ? <p>No assessments saved in this browser yet. <Link to="/assess">Assess an image</Link> to begin.</p> :
        query.isPending ? <p>Loading saved samples…</p> :
        query.isError ? <p role="alert">Could not load samples from the assessment service.</p> : <>
          {samples.length < ids.length && <p role="status">Some saved samples could not be retrieved.</p>}
          <div className="sample-list-grid">
            {samples.map((sample) => <Link className="card" key={sample.sample_id} to={`/samples/${sample.sample_id}`}>
              <h2>Sample {sample.sample_id}</h2>
              <p>{sample.captured_at || sample.created_at || "Capture time unavailable"}</p>
              <p>Image quality: {sample.quality?.status ?? "Unavailable"}</p>
              <p>Road score: {sample.score?.value == null ? "Unavailable" : `${sample.score.value} / 100`}</p>
            </Link>)}
          </div>
        </>}
    </div>
  );
}
