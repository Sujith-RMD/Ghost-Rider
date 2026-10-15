import { useEffect, useRef, useState } from "react";
import type { Bin } from "../api/display";
import { numeric } from "../lib/metric";
import {
  MetricValue,
  ConditionChip,
  SourceModeChip,
  SevereDefectFlag,
} from "./primitives";
import { useSelection } from "../app/store";
export function SegmentTable({ bins }: { bins: Bin[] }) {
  const [reverse, setReverse] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [heights, setHeights] = useState<Record<string, number>>({});
  const select = useSelection((s) => s.selectBin);
  const selected = useSelection((s) => s.binId);
  const sorted = [...bins].sort(
    (a, b) => (numeric(a.start) ?? 0) - (numeric(b.start) ?? 0),
  );
  if (reverse) sorted.reverse();
  const virtual = bins.length > 200;
  const offsets = [0];
  for (const bin of sorted)
    offsets.push(offsets[offsets.length - 1] + (heights[bin.id] ?? 110));
  const first = virtual
    ? Math.max(0, offsets.findIndex((v) => v >= scrollTop) - 5)
    : 0;
  const stop = virtual
    ? Math.min(
        sorted.length,
        Math.max(first + 1, offsets.findIndex((v) => v > scrollTop + 520) + 5),
      )
    : sorted.length;
  const visible = sorted.slice(first, stop);
  useEffect(() => {
    if (!virtual || !viewport.current) return;
    const observer = new ResizeObserver((entries) => {
      setHeights((previous) => {
        let updated = previous;
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.binId!;
          const height = entry.target.getBoundingClientRect().height;
          if (previous[id] !== height) updated = { ...updated, [id]: height };
        }
        return updated;
      });
    });
    viewport.current
      .querySelectorAll("tr[data-bin-id]")
      .forEach((row) => observer.observe(row));
    return () => observer.disconnect();
  }, [virtual, first, stop, reverse]);
  return (
    <>
      <div
        className="table-scroll"
        ref={viewport}
        style={virtual ? { maxHeight: 520, overflow: "auto" } : undefined}
        onScroll={
          virtual ? (e) => setScrollTop(e.currentTarget.scrollTop) : undefined
        }
      >
        <table aria-rowcount={sorted.length + 1}>
          <caption>
            Sampled-strip reporting bins. Unknown stretches carry no condition
            claim.
          </caption>
          <thead>
            <tr>
              <th>
                <button
                  className="text-button"
                  onClick={() => {
                    setReverse(!reverse);
                    setScrollTop(0);
                    viewport.current?.scrollTo({ top: 0 });
                  }}
                >
                  Bin {reverse ? "↑" : "↓"}
                </button>
              </th>
              <th>Distance</th>
              <th>Accepted samples</th>
              <th>Strip area</th>
              <th>Median</th>
              <th>Lower tail</th>
              <th>Flags</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {virtual && first > 0 && (
              <tr aria-hidden="true">
                <td
                  colSpan={8}
                  style={{ height: offsets[first], padding: 0, border: 0 }}
                />
              </tr>
            )}
            {visible.map((b) => (
              <tr
                key={b.id}
                data-bin-id={b.id}
                aria-rowindex={sorted.indexOf(b) + 2}
                className={selected === b.id ? "selected" : ""}
              >
                <td>
                  <button
                    className="text-button"
                    onClick={() => select(b.id)}
                    aria-pressed={selected === b.id}
                  >
                    {b.id}
                  </button>
                  <SourceModeChip mode={b.mode} />
                </td>
                <td>
                  <MetricValue metric={b.start} />
                  <span className="muted">to </span>
                  <MetricValue metric={b.end} />
                </td>
                <td>
                  <MetricValue metric={b.accepted} />
                </td>
                <td>
                  <MetricValue metric={b.area} />
                </td>
                <td>
                  <MetricValue metric={b.median} />
                </td>
                <td>
                  <MetricValue metric={b.lower} />
                </td>
                <td>
                  {b.sampled ? (
                    <ConditionChip condition={b.condition} score={b.median} />
                  ) : (
                    <span>Not sampled</span>
                  )}
                  {b.severe && <SevereDefectFlag />}
                </td>
                <td>
                  <MetricValue metric={b.coverage} />
                </td>
              </tr>
            ))}
            {virtual && stop < sorted.length && (
              <tr aria-hidden="true">
                <td
                  colSpan={8}
                  style={{
                    height: offsets[sorted.length] - offsets[stop],
                    padding: 0,
                    border: 0,
                  }}
                />
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
