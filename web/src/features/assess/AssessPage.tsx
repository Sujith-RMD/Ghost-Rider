import { useEffect, useRef, useState } from "react";
import { UploadCloud, FileImage } from "lucide-react";
import { AbstractBackdrop } from "../../components/AbstractBackdrop";
import { DevFixturePanel } from "virtual:roadsight-data";
import { Link } from "react-router-dom";
import type { JobState, Session } from "../../api/display";
import { apiBase, readJob, readSample, startAssessment, type ActualSample } from "../../api/real-assessment";
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
  session?: Session;
  mock: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState("Reading native dimensions");
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<JobState>("received");
  const [started, setStarted] = useState(false);
  const [jobId, setJobId] = useState<string | null>(() => mock ? null : sessionStorage.getItem("roadsight.activeJob"));
  const [sample, setSample] = useState<ActualSample | null>(null);
  const [running, setRunning] = useState(false);
  const [validImage, setValidImage] = useState(false);
  const [pollAttempt, setPollAttempt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  useEffect(() => {
    if (!jobId || mock) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const job = await readJob(jobId);
        if (cancelled) return;
        setError(null);
        setStarted(true);
        setState(job.status);
        if (job.status === "failed") {
          setError(job.error_reason || "Analysis failed.");
          setRunning(false);
          return;
        }
        if (job.status === "partial" || job.status === "succeeded") {
          if (job.result_sample_id) setSample(await readSample(job.result_sample_id));
          setRunning(false);
          return;
        }
        timer = setTimeout(poll, 1200);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Could not check analysis status.");
          setRunning(false);
        }
      }
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [jobId, mock, pollAttempt]);
  async function analyse() {
    if (!file || !validImage || mock || submitting.current) return;
    submitting.current = true;
    setError(null);
    setSample(null);
    setRunning(true);
    setStarted(true);
    setState("received");
    try {
      const id = await startAssessment(file);
      sessionStorage.setItem("roadsight.activeJob", id);
      setJobId(id);
      setState("queued");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed.");
      setState("failed");
      setRunning(false);
    } finally {
      submitting.current = false;
    }
  }
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    const image = new Image();
    setValidImage(false);
    image.onload = () => {
      setValidImage(true);
      setDimensions(
        `${image.naturalWidth} × ${image.naturalHeight} native pixels`,
      );
    };
    image.onerror = () => {
      setValidImage(false);
      setError("This image could not be decoded. Choose a valid JPEG or PNG.");
    };
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function choose(next: File | undefined) {
    if (!next) return;
    if (!["image/jpeg", "image/png"].includes(next.type)) {
      setFile(null);
      setValidImage(false);
      setError("Choose a JPEG or PNG image.");
      return;
    }
    if (!next.size || next.size > 25 * 1024 * 1024) {
      setFile(null);
      setValidImage(false);
      setError("Choose an image smaller than 25 MB.");
      return;
    }
    setError(null);
    setFile(next);
    setStarted(false);
    setSample(null);
    setJobId(null);
    sessionStorage.removeItem("roadsight.activeJob");
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
                Maximum 25 MB. Use a verified camera
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
              {mock
                ? "Fixture preview; values are not measurements."
                : file
                  ? "Selected image ready for the real assessment service."
                  : jobId
                    ? "Checking your previous analysis job."
                    : "Choose an image to start an assessment. Originals and evidence stay separate."}
            </p>
            <div className="analysis-action">
              <button
                className="button primary"
                disabled={mock || !file || !validImage || running}
                onClick={() => void analyse()}
              >
                Analyse image
              </button>
              <span>
                {running ? "Uploading or analysing…" : mock ? "Fixture mode; real upload is disabled." : file ? "The uploaded image will be processed by the backend." : "Choose an image to continue."}
              </span>
            </div>
            {started ? (
              <JobStepper
                state={state}
                reason={
                  state === "partial"
                    ? "Analysis is incomplete; score or calibrated measurements may be unavailable."
                    : state === "failed"
                      ? error || "Analysis failed. Choose a valid image and retry."
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
            {!mock && jobId && error && (
              <button className="button secondary" onClick={() => setPollAttempt((attempt) => attempt + 1)}>
                Check job again
              </button>
            )}
            {mock && started && state === "succeeded" && (
              <Link
                className="button primary"
                to={`/samples/${session?.samples[0]?.id}`}
              >
                Open fixture evidence
              </Link>
            )}
            {!mock && sample && (
              <div className="actual-result" aria-live="polite">
                <h3>Assessment evidence</h3>
                {sample.image_url && <img src={new URL(sample.image_url, apiBase).toString()} alt="Original uploaded road image" />}
                <p>Image quality: {sample.quality?.status ?? "Unavailable"}</p>
                {!!sample.quality?.reasons?.length && <p>Quality reasons: {sample.quality.reasons.join(", ")}</p>}
                <p>Road score: {sample.score?.value == null ? "Unavailable — scoring is not implemented for this image" : `${sample.score.value} / 100 (${sample.score.status})`}</p>
                <p>Physical scale: {sample.geometry_valid ? "Validated" : "Uncalibrated; physical units unavailable"}</p>
                <p>Exploratory visible instance count (not validated): {sample.metrics?.chip_count ?? "Unavailable"}</p>
                <p>Count per m²: {sample.metrics?.chip_density_per_m2 ?? "Unavailable without calibrated area"}</p>
                {sample.error && <p>Analysis limitation: {sample.error}</p>}
                <p>Model: {sample.model_version ?? "Unavailable"}</p>
                {sample.sample_id && <Link className="button secondary" to={`/samples/${sample.sample_id}`}>Open sample detail</Link>}
              </div>
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
