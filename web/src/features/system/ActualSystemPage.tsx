import { useEffect, useState } from "react";
import { readHealth, type ActualHealth } from "../../api/real-assessment";
import { Card } from "../../components/primitives";
import { CONTRACT_VERSION } from "../../contract/version";

export default function ActualSystemPage() {
  const [health, setHealth] = useState<ActualHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    readHealth().then(
      (result) => { if (active) setHealth(result); },
      (cause) => { if (active) setError(cause instanceof Error ? cause.message : "Health check failed."); },
    );
    return () => { active = false; };
  }, []);

  return (
    <div className="content-page">
      <div className="page-heading"><div><h1>System readiness</h1><p>Live service status and remaining validation gates.</p></div></div>
      <Card title="Assessment service">
        {error ? <p role="alert">{error}</p> : !health ? <p>Checking service…</p> : (
          <dl>
            <div><dt>API</dt><dd>{health.status}</dd></div>
            <div><dt>Contract version</dt><dd>{health.version === CONTRACT_VERSION ? `${health.version} (matched)` : `${health.version} (client expects ${CONTRACT_VERSION})`}</dd></div>
            {Object.entries(health.services ?? {}).map(([name, value]) => (
              <div key={name}><dt>{name}</dt><dd>{typeof value === "object" && value !== null && "status" in value ? String(value.status) : "Unavailable"}</dd></div>
            ))}
          </dl>
        )}
      </Card>
      <Card title="External validation">
        <p>Google Maps: {import.meta.env.VITE_GOOGLE_MAPS_API_KEY ? "Key configured; real GPS route unverified." : "Key not configured."}</p>
        <p>Live Indian road camera: access and capture unverified.</p>
        <p>Physical calibration and scored condition: pending ML validation.</p>
      </Card>
    </div>
  );
}
