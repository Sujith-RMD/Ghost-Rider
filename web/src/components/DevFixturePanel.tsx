import { useRef, useState } from "react";
import { SlidersHorizontal, X, Check } from "lucide-react";
import type { JobState } from "../api/display";

export default function DevFixturePanel({
  state,
  onChange,
}: {
  state: JobState;
  onChange: (value: JobState) => void;
}) {
  const [open, setOpen] = useState(
    new URLSearchParams(location.search).get("dev") === "1",
  );
  const [focused, setFocused] = useState(0);
  const options = useRef<(HTMLButtonElement | null)[]>([]);
  const states: JobState[] = [
    "received",
    "validated",
    "queued",
    "processing",
    "succeeded",
    "partial",
    "failed",
  ];
  return (
    <div className="dev-fixture-tools" data-dev-fixtures="true">
      <button
        className="dev-tools-trigger"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="fixture-panel"
      >
        <SlidersHorizontal size={16} />
        UI fixtures
      </button>
      {open && (
        <section
          id="fixture-panel"
          className="dev-fixture-panel card"
          aria-label="Development fixture controls"
        >
          <div className="card-heading">
            <h2>Development fixtures</h2>
            <button
              className="icon-button"
              aria-label="Close fixture controls"
              onClick={() => setOpen(false)}
            >
              <X size={16} />
            </button>
          </div>
          <p>
            Changes preview state only. Your selected image is not analysed.
          </p>
          <div
            role="listbox"
            aria-label="Example outcome"
            className="fixture-listbox"
            onKeyDown={(e) => {
              const delta =
                e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
              if (delta) {
                e.preventDefault();
                const next = (focused + delta + states.length) % states.length;
                setFocused(next);
                options.current[next]?.focus();
              }
            }}
          >
            {states.map((value, i) => (
              <button
                role="option"
                aria-selected={value === state}
                tabIndex={i === focused ? 0 : -1}
                key={value}
                ref={(el) => {
                  options.current[i] = el;
                }}
                onClick={() => {
                  setFocused(i);
                  onChange(value);
                }}
              >
                {value[0].toUpperCase() + value.slice(1)}
                {value === state && <Check size={14} />}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
