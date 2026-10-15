import { useEffect, useRef, useState } from "react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import type { Sample } from "../api/display";
import { MetricValue } from "./primitives";
export function EvidenceViewer({ sample }: { sample: Sample }) {
  const [active, setActive] = useState<string[]>(
    sample.layers.filter((l) => l.url).map((l) => l.id),
  );
  const [opacity, setOpacity] = useState(55);
  const [compare, setCompare] = useState(100);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [fullscreen, setFullscreen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const fitZoom = useRef(1);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const previousDistance = useRef<number | null>(null);
  useEffect(() => {
    if (!fullscreen) return;
    const before = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
      if (e.key === "Tab") {
        const controls = panel.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),[tabindex="0"]',
        );
        if (!controls?.length) return;
        const first = controls[0],
          last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      before?.focus();
    };
  }, [fullscreen]);
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const fit = () => {
      const value = Math.min(
        element.clientWidth / sample.width,
        element.clientHeight / sample.height,
        1,
      );
      fitZoom.current = value;
      setZoom(value);
      setPan({ x: 0, y: 0 });
    };
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    fit();
    return () => observer.disconnect();
  }, [sample.width, sample.height, fullscreen]);
  function changeZoom(delta: number) {
    setZoom((z) => Math.min(5, Math.max(0.1, z + delta)));
  }
  return (
    <div
      className={`evidence-viewer ${fullscreen ? "fullscreen" : ""}`}
      ref={panel}
      tabIndex={fullscreen ? -1 : undefined}
      role={fullscreen ? "dialog" : undefined}
      aria-modal={fullscreen ? true : undefined}
      aria-label="Evidence viewer"
    >
      <div className="viewer-toolbar">
        <div>
          <h2>Surface evidence</h2>
          <p>
            {sample.width} × {sample.height} native pixels /{" "}
            {Math.round(zoom * 100)}% zoom
          </p>
        </div>
        <button
          className="icon-button"
          onClick={() => setFullscreen(!fullscreen)}
          aria-label={
            fullscreen
              ? "Close full-screen evidence"
              : "Open full-screen evidence"
          }
        >
          <Maximize2 size={18} />
        </button>
      </div>
      {sample.schematic && (
        <div className="schematic-notice">
          Schematic fixture. This is not captured road evidence.
        </div>
      )}
      <div className="layer-toggles">
        {sample.layers.map((l) => (
          <label
            key={l.id}
            className={l.url ? "" : "disabled"}
            title={l.reason}
          >
            <input
              type="checkbox"
              disabled={!l.url}
              checked={active.includes(l.id)}
              onChange={() =>
                setActive((a) =>
                  a.includes(l.id)
                    ? a.filter((id) => id !== l.id)
                    : [...a, l.id],
                )
              }
            />
            {l.name}
            {!l.url && <small>{l.reason}</small>}
          </label>
        ))}
      </div>
      <div
        className="image-viewport"
        ref={viewport}
        tabIndex={0}
        aria-label="Pan and zoom evidence. Use plus, minus, zero, or arrow keys."
        onWheel={(e) => {
          if (e.ctrlKey) {
            e.preventDefault();
            changeZoom(-e.deltaY * 0.003);
          }
        }}
        onKeyDown={(e) => {
          if (
            [
              "+",
              "=",
              "-",
              "0",
              "ArrowLeft",
              "ArrowRight",
              "ArrowUp",
              "ArrowDown",
            ].includes(e.key)
          )
            e.preventDefault();
          if (e.key === "+" || e.key === "=") changeZoom(0.2);
          if (e.key === "-") changeZoom(-0.2);
          if (e.key === "0") {
            setZoom(fitZoom.current);
            setPan({ x: 0, y: 0 });
          }
          if (e.key.startsWith("Arrow"))
            setPan((p) => ({
              x:
                p.x +
                (e.key === "ArrowLeft" ? 20 : e.key === "ArrowRight" ? -20 : 0),
              y:
                p.y +
                (e.key === "ArrowUp" ? 20 : e.key === "ArrowDown" ? -20 : 0),
            }));
        }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          pointer.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
          pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        }}
        onPointerMove={(e) => {
          if (!pointers.current.has(e.pointerId)) return;
          pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
          if (pointers.current.size === 2) {
            const [a, b] = [...pointers.current.values()];
            const d = Math.hypot(a.x - b.x, a.y - b.y);
            if (previousDistance.current)
              changeZoom((d - previousDistance.current) / 150);
            previousDistance.current = d;
          } else if (pointer.current)
            setPan({
              x: e.clientX - pointer.current.x,
              y: e.clientY - pointer.current.y,
            });
        }}
        onPointerUp={(e) => {
          pointers.current.delete(e.pointerId);
          pointer.current = null;
          previousDistance.current = null;
        }}
        onPointerCancel={() => {
          pointers.current.clear();
          pointer.current = null;
          previousDistance.current = null;
        }}
      >
        {sample.image ? (
          <div
            className="image-transform"
            style={{
              width: sample.width,
              height: sample.height,
              transform: `translate(calc(-50% + ${pan.x}px),calc(-50% + ${pan.y}px)) scale(${zoom})`,
            }}
          >
            <img
              src={sample.image}
              alt={
                sample.schematic
                  ? "Synthetic pavement-like geometry for interface testing only"
                  : "Original road image"
              }
              draggable={false}
            />
            <div
              className="overlay-stack"
              style={{ clipPath: `inset(0 ${100 - compare}% 0 0)` }}
            >
              {sample.layers
                .filter((l) => l.url && active.includes(l.id))
                .map((l) => (
                  <img
                    key={l.id}
                    src={l.url}
                    alt={`${l.name}, ${l.pattern} pattern; denominator: ${l.denominator}`}
                    style={{ opacity: opacity / 100 }}
                    draggable={false}
                  />
                ))}
            </div>
          </div>
        ) : (
          <p>No original image supplied.</p>
        )}
        <div className="zoom-controls">
          <button
            aria-label="Zoom out evidence"
            onClick={() => changeZoom(-0.2)}
          >
            <Minus size={16} />
          </button>
          <button
            aria-label="Reset evidence view"
            onClick={() => {
              setZoom(fitZoom.current);
              setPan({ x: 0, y: 0 });
            }}
          >
            <RotateCcw size={16} />
          </button>
          <button aria-label="Zoom in evidence" onClick={() => changeZoom(0.2)}>
            <Plus size={16} />
          </button>
        </div>
      </div>
      <div className="viewer-sliders">
        <label>
          Compare original / overlays
          <input
            type="range"
            min="0"
            max="100"
            value={compare}
            onChange={(e) => setCompare(+e.target.value)}
          />
        </label>
        <label>
          Overlay opacity {opacity}%
          <input
            type="range"
            min="0"
            max="100"
            value={opacity}
            onChange={(e) => setOpacity(+e.target.value)}
          />
        </label>
      </div>
      <div className="evidence-legend">
        <p>
          Scale source: <MetricValue metric={sample.scale} />
          {sample.calibrated ? " (fixture calibration)" : ""}
        </p>
        {sample.layers
          .filter((l) => l.url && active.includes(l.id))
          .map((l) => (
            <div key={l.id}>
              <i className={`layer-swatch ${l.pattern}`} />
              <span>
                {l.name}
                <small>Denominator: {l.denominator}</small>
              </span>
              <MetricValue metric={l.area} />
            </div>
          ))}
      </div>
    </div>
  );
}
