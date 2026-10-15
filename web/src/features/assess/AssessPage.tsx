import { useEffect, useRef, useState } from "react";
import { UploadCloud, FileImage } from "lucide-react";
import { AbstractBackdrop } from "../../components/AbstractBackdrop";
import { DevFixturePanel } from "virtual:roadsight-data";
import { Link } from "react-router-dom";
import type { JobState, Session } from "../../api/display";
import {
  Card,
  ErrorPanel,
  JobStepper,
  SourceModeChip,
} from "../../components/primitives";
export default function AssessPage({
  session,
  mock,
}: {
  session: Session;
  mock: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState("Reading native dimensions");
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<JobState>("received");
  const [started, setStarted] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    const image = new Image();
    image.onload = () =>
      setDimensions(
        `${image.naturalWidth} × ${image.naturalHeight} native pixels`,
      );
    image.onerror = () =>
      setError("This image could not be decoded. Choose a valid JPEG or PNG.");
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function choose(next: File | undefined) {
    if (!next) return;
    if (!["image/jpeg", "image/png"].includes(next.type)) {
      setError("Choose a JPEG or PNG image.");
      return;
    }
    setError(null);
    setFile(next);
    setStarted(false);
  }
  return (
    <div className="content-page assess-page">
      <div className="page-heading">
        <div>
          <h1>Assess a surface</h1>
          <p>Start with an image. Follow the evidence.</p>
        </div>
        <SourceModeChip mode="still" />
      </div>
      <div className="two-columns assess-columns">
        <div>
          <Card title="Choose an image">
            <div
              className={`dropzone ${file ? "has-file" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                choose(e.dataTransfer.files[0]);
              }}
            >
              <AbstractBackdrop compact />
              <span className="viewfinder-tick top-left" />
              <span className="viewfinder-tick top-right" />
              <span className="viewfinder-tick bottom-left" />
              <span className="viewfinder-tick bottom-right" />
              {preview ? (
                <img
                  src={preview}
                  alt="Selected local image preview, not yet analysed"
                />
              ) : (
                <UploadCloud size={36} />
              )}
              <h3>{file ? file.name : "Drop a road image here"}</h3>
              <p>
                {file
                  ? `${dimensions} / ${(file.size / 1024 / 1024).toFixed(2)} MB`
                  : "JPEG or PNG. The original stays intact."}
              </p>
              <button
                className="button secondary"
                onClick={() => input.current?.click()}
              >
                <FileImage size={16} />
                {file ? "Choose another image" : "Browse images"}
              </button>
              <input
                ref={input}
                className="sr-only"
                type="file"
                accept="image/jpeg,image/png"
                aria-label="Choose road image"
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </div>
            <div className="upload-requirements">
              <span>JPEG / PNG</span>
              <p>
                Upload limit awaiting confirmation. Use a verified camera
                profile or scale reference for physical measurements.
              </p>
            </div>
            {error && (
              <ErrorPanel
                family="validation"
                title={error}
                retry={() => input.current?.click()}
              />
            )}
          </Card>
        </div>
        <div className="assessment-workflow">
          <Card title="Analysis progress">
            <p>
              {file
                ? "Image selected. The analysis service is not connected yet."
                : "Choose an image to start an assessment. Originals and evidence stay separate."}
            </p>
            <div className="analysis-action">
              <button
                className="button primary"
                disabled
                title="Backend upload and finalize schemas are not published"
              >
                Analyse image
              </button>
              <span>
                {file
                  ? "Analysis service not connected."
                  : "Choose an image to continue."}
              </span>
            </div>
            {started ? (
              <JobStepper
                state={state}
                reason={
                  state === "partial"
                    ? "Scale not calibrated. Density unavailable."
                    : state === "failed"
                      ? "Fixture worker failure. Retry the real analysis when connected."
                      : undefined
                }
              />
            ) : (
              <div
                className="idle-job-stepper"
                aria-label="Analysis has not started"
              >
                <ol>
                  {[
                    "Received",
                    "Validated",
                    "Queued",
                    "Processing",
                    "Result",
                  ].map((stage) => (
                    <li key={stage}>
                      <span />
                      {stage}
                    </li>
                  ))}
                </ol>
                <p>Analysis has not started.</p>
              </div>
            )}
            {started && state === "succeeded" && (
              <Link
                className="button primary"
                to={`/samples/${session.samples[0]?.id}`}
              >
                Open fixture evidence
              </Link>
            )}
          </Card>
          <Card title="Before you measure">
            <ul className="plain-list">
              <li>
                Include GPS in the file or enter verified coordinates when
                supported.
              </li>
              <li>
                Wet, blurred or unsupported surfaces may return a limited
                result.
              </li>
              <li>
                Local camera access and Indian transfer have not been validated.
              </li>
            </ul>
            <div className="measurement-note">
              <span className="chip">Evidence first</span>
              <p>A successful upload is not a completed analysis.</p>
            </div>
          </Card>
        </div>
      </div>
      {mock && (
        <DevFixturePanel
          state={state}
          onChange={(value) => {
            setState(value);
            setStarted(true);
          }}
        />
      )}
    </div>
  );
}
