import type { components } from "../contract/generated";

type DetectionEvidence = components["schemas"]["DistressDetectionEvidence"] | null | undefined;

export function DistressDetectionOverlay({
  imageUrl,
  evidence,
}: {
  imageUrl: string;
  evidence: DetectionEvidence;
}) {
  const detections = evidence?.detections ?? [];
  return (
    <section className="distress-detection" aria-label="Distress detection evidence">
      <h3>India distress detector</h3>
      <div className="detection-image-frame">
        <img src={imageUrl} alt="Original uploaded road image" />
        {evidence?.status === "success" && evidence.image_width && evidence.image_height && detections.length > 0 && (
          <svg
            className="detection-boxes"
            viewBox={`0 0 ${evidence.image_width} ${evidence.image_height}`}
            preserveAspectRatio="none"
            role="img"
            aria-label="Distress detection boxes"
          >
            {detections.map((detection, index) => {
              const [x1, y1, x2, y2] = detection.bbox_xyxy;
              return (
                <g key={`${detection.class_id}-${index}`} role="img" aria-label={`Detected ${detection.class_name}`}>
                  <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} />
                  <text x={x1} y={Math.max(14, y1 - 4)}>{detection.class_name} {Math.round(detection.confidence * 100)}%</text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
      {!evidence ? (
        <p>Detection evidence was not recorded for this sample.</p>
      ) : evidence.status !== "success" ? (
        <p role="status">India distress detection unavailable: {evidence.reason ?? "inference_error"}.</p>
      ) : (
        <>
          <p>
            Model {evidence.model_version ?? "unknown"}
            {evidence.model_sha256 ? ` · SHA-256 ${evidence.model_sha256.slice(0, 12)}` : ""}
            {evidence.inference_ms != null ? ` · ${Math.round(evidence.inference_ms)} ms` : ""}
          </p>
          {detections.length ? (
            <ul className="detection-list" aria-label="Detected distress classes">
              {detections.map((detection, index) => (
                <li key={`${detection.class_id}-${index}`}>
                  {detection.class_name} · {Math.round(detection.confidence * 100)}%
                </li>
              ))}
            </ul>
          ) : (
            <p>No distress boxes detected by the configured model.</p>
          )}
          <p className="detection-limit">
            Detection boxes show localization. They are not masks, physical measurements, or a road-quality score.
          </p>
        </>
      )}
    </section>
  );
}
