import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { createLiveSession, finishSession, readSession, sendFrame, type ActualSession } from "../../api/real-assessment";
import { rememberSample } from "../../api/recent-samples";
import { Card } from "../../components/primitives";

export default function ActualLivePage() {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const current = useRef<ActualSession | null>(null);
  const mounted = useRef(true);
  const starting = useRef(false);
  const [session, setSession] = useState<ActualSession | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = useCallback((value: ActualSession) => {
    current.current = value;
    if (mounted.current) setSession(value);
    if (value.latest_sample_id) rememberSample(value.latest_sample_id);
  }, []);
  const releaseCamera = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    if (mounted.current) { setRunning(false); setReady(false); }
  }, []);
  const stop = useCallback(async () => {
    releaseCamera();
    const value = current.current;
    if (value && value.status !== "finished") update(await finishSession(value.session_id));
  }, [releaseCamera, update]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      releaseCamera();
      const value = current.current;
      if (value && value.status !== "finished") void finishSession(value.session_id).catch(() => {});
    };
  }, [releaseCamera]);

  async function start() {
    if (starting.current) return;
    starting.current = true;
    setBusy(true); setError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera access requires localhost or HTTPS and a supported browser.");
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      if (!mounted.current) { media.getTracks().forEach((track) => track.stop()); return; }
      stream.current = media;
      const value = await createLiveSession(media.getVideoTracks()[0]?.label || "Browser camera");
      if (!mounted.current) { releaseCamera(); await finishSession(value.session_id); return; }
      update(value);
      if (video.current) video.current.srcObject = media;
      media.getVideoTracks().forEach((track) => { track.onended = () => { void stop().catch((cause: Error) => setError(cause.message)); }; });
      setRunning(true);
    } catch (cause) {
      releaseCamera();
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Could not start the camera. Check camera permission and connection.");
    } finally {
      starting.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  const sessionId = session?.session_id;
  useEffect(() => {
    if (!sessionId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await readSession(sessionId!, controller.signal);
        if (controller.signal.aborted) return;
        update(value);
        if (value.status === "finished" && value.processed_count + value.rejected_count + value.dropped_count >= value.frame_count) return;
        timer = setTimeout(() => void poll(), 1500);
      } catch (cause) {
        if (!controller.signal.aborted) {
          releaseCamera();
          setError(`Session connection lost. ${cause instanceof Error ? cause.message : "Check the assessment service."}`);
          void finishSession(sessionId!).catch(() => {});
        }
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [sessionId, update, releaseCamera]);

  useEffect(() => {
    if (!running || !ready || !sessionId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let waitingSince = Date.now();
    async function capture() {
      try {
        const value = current.current;
        const pending = value && value.frame_count > value.processed_count + value.rejected_count + value.dropped_count;
        if (pending) {
          if (Date.now() - waitingSince > 60000) throw new Error("Processing has not completed for 60 seconds. Capture stopped to avoid building a queue.");
          timer = setTimeout(() => void capture(), 1500);
          return;
        }
        const camera = video.current;
        if (!camera?.videoWidth || !camera.videoHeight) throw new Error("The camera is not providing frames. Reconnect it and start again.");
        const canvas = document.createElement("canvas");
        canvas.width = camera.videoWidth; canvas.height = camera.videoHeight;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("This browser cannot capture camera frames.");
        const capturedAt = new Date().toISOString();
        context.drawImage(camera, 0, 0);
        const frame = await new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Could not encode the camera frame.")), "image/jpeg", 0.9));
        if (controller.signal.aborted) return;
        const received = await sendFrame(sessionId!, frame, capturedAt, controller.signal);
        if (controller.signal.aborted) return;
        update(received);
        waitingSince = Date.now();
        timer = setTimeout(() => void capture(), 5000);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Frame transmission failed.");
          void stop().catch((failure: Error) => setError(failure.message));
        }
      }
    }
    void capture();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [running, ready, sessionId, update, stop]);

  return <div className="content-page">
    <div className="page-heading"><div><h1>Live road capture</h1><p>Connect a camera. Send real frames. Follow processing.</p></div><span className="chip">{running ? "Camera connected" : "Camera off"}</span></div>
    <div className="two-columns live-columns">
      <Card title="Camera preview">
        <video ref={video} autoPlay muted playsInline aria-label="Live camera preview" onLoadedMetadata={() => setReady(true)} onError={() => { setError("Camera preview failed. Reconnect the camera."); void stop().catch(() => {}); }} style={{ width: "100%", aspectRatio: "16 / 9", background: "var(--surface-2)", borderRadius: 16, objectFit: "contain" }} />
        <p>Frames are sent at most every five seconds. Capture waits while the previous frame is being processed.</p>
        <button className="button primary" disabled={busy || running} onClick={() => void start()}>{busy ? "Connecting camera…" : "Start camera"}</button>{" "}
        <button className="button secondary" disabled={!running} onClick={() => void stop().catch((cause: Error) => setError(cause.message))}>Stop session</button>
        {error && <p role="alert">{error}</p>}
      </Card>
      <div>
        <Card title="Session monitor">
          <p aria-live="polite">{busy ? "Waiting for camera access." : running ? ready ? "Live capture running." : "Waiting for camera frames." : session ? "Camera stopped. Stored frames remain available." : "Start the camera to create a live session."}</p>
          <dl>
            <div><dt>Received</dt><dd>{session?.frame_count ?? 0}</dd></div>
            <div><dt>Processed</dt><dd>{session?.processed_count ?? 0}</dd></div>
            <div><dt>Rejected</dt><dd>{session?.rejected_count ?? 0}</dd></div>
            <div><dt>Dropped</dt><dd>{session?.dropped_count ?? 0}</dd></div>
            <div><dt>Last capture</dt><dd>{session?.last_capture_at || "No frame received"}</dd></div>
            <div><dt>Last processed</dt><dd>{session?.last_processed_at || "No processed frame"}</dd></div>
          </dl>
          {session?.latest_sample_id && <Link className="button secondary" to={`/samples/${session.latest_sample_id}`}>Open latest evidence</Link>}
        </Card>
        <Card title="Measurement limits"><p>Use a road-facing camera. This camera has no verified calibration or GPS feed: physical size, inclination, route coverage and validated road scores remain unavailable.</p><p>This is sampled live capture; continuous road coverage has not been established.</p></Card>
      </div>
    </div>
  </div>;
}
