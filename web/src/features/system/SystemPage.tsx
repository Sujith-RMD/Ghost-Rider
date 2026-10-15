import type { Health } from "../../api/display";
import { Card } from "../../components/primitives";
export default function SystemPage({
  health,
  contractVersion,
}: {
  health: Health[];
  contractVersion: string | null;
}) {
  return (
    <div className="content-page">
      <div className="page-heading">
        <div>
          <h1>System readiness</h1>
          <p>Readiness is reported independently of interface availability.</p>
        </div>
      </div>
      <Card title="Backend services">
        <div className="health-rows">
          {health.map((h) => (
            <div className="health-row" key={h.name}>
              <span
                className={`health-indicator ${h.state}`}
                role="img"
                aria-label={h.state}
              />
              <div>
                <h3>{h.name}</h3>
                <p>{h.detail}</p>
              </div>
              <span>{h.checkedAt ?? "Not checked"}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Browser integration">
        <div className="health-row">
          <span className="health-indicator unavailable" />
          <div>
            <h3>Google Maps</h3>
            <p>
              {import.meta.env.VITE_GOOGLE_MAPS_API_KEY
                ? "Key configured; real GPS route and authorized tile load still require verification."
                : "Browser key not configured. Map tiles have not been loaded."}
            </p>
          </div>
          <span>Unverified</span>
        </div>
      </Card>
      <Card title="Contract and measurement gates">
        <dl>
          <div>
            <dt>Client OpenAPI version</dt>
            <dd>{contractVersion ?? "Not published"}</dd>
          </div>
          <div>
            <dt>Server version / compatibility</dt>
            <dd>Not checked</dd>
          </div>
          <div>
            <dt>Live camera access</dt>
            <dd>Unverified</dd>
          </div>
          <div>
            <dt>Calibrated chip detail</dt>
            <dd>Unverified</dd>
          </div>
          <div>
            <dt>Physical grade</dt>
            <dd>Unsupported</dd>
          </div>
          <div>
            <dt>Indian-domain transfer</dt>
            <dd>Not validated</dd>
          </div>
          <div>
            <dt>Queue depth</dt>
            <dd>Not supplied</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
