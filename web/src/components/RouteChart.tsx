import { useId, useState } from "react";
import { LinePath } from "@visx/shape";
import { scaleLinear } from "@visx/scale";
import type { Bin, Session } from "../api/display";
import { numeric } from "../lib/metric";
import { MetricValue, ScoreLabel } from "./primitives";
import { useSelection } from "../app/store";
export function conditionRuns(bins: Bin[]): Bin[][] {
  const runs: Bin[][] = [];
  let run: Bin[] = [];
  for (const b of bins) {
    if (
      !b.sampled ||
      numeric(b.accepted) === 0 ||
      numeric(b.median) === undefined
    ) {
      if (run.length) runs.push(run);
      run = [];
    } else run.push(b);
  }
  if (run.length) runs.push(run);
  return runs;
}
export function RouteChart({
  session,
  compact = false,
}: {
  session: Session;
  compact?: boolean;
}) {
  const [table, setTable] = useState(false);
  const id = useId().replaceAll(":", "");
  const select = useSelection((s) => s.selectBin);
  const selected = useSelection((s) => s.binId);
  const width = compact ? 376 : 960,
    height = compact ? 140 : 270;
  const x = scaleLinear({
    domain: [0, numeric(session.length) ?? 1],
    range: [34, width - 14],
  });
  const all = session.bins.flatMap((b) =>
    numeric(b.median) === undefined ? [] : [numeric(b.median)!],
  );
  const domain = all.length
    ? [Math.max(0, Math.min(...all) - 12), Math.max(...all) + 10]
    : [0, 1];
  const y = scaleLinear({ domain, range: [height - 34, 20] });
  const runs = conditionRuns(session.bins);
  return (
    <div className={`route-chart ${compact ? "compact" : ""}`}>
      <div className="chart-summary">
        <div>
          <MetricValue metric={session.median} hero />
          <ScoreLabel status={session.scoreStatus} />
        </div>
        <button
          className="text-button"
          onClick={() => setTable(!table)}
          aria-expanded={table}
        >
          {table ? "Hide data" : "View data"}
        </button>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="group"
        aria-label="Condition along route distance. The line breaks where no accepted samples exist."
      >
        <defs>
          <pattern
            id={`hatch-${id}`}
            width="8"
            height="8"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(35)"
          >
            <line
              x1="0"
              x2="0"
              y1="0"
              y2="8"
              stroke="currentColor"
              strokeOpacity=".16"
            />
          </pattern>
        </defs>
        {y.ticks(3).map((value) => (
          <g key={value}>
            <line
              x1="34"
              x2={width - 14}
              y1={y(value)}
              y2={y(value)}
              className="chart-grid"
            />
            <text x="24" y={y(value) + 4} textAnchor="end">
              {value}
            </text>
          </g>
        ))}
        {session.bins
          .filter((b) => b.severe && b.sampled)
          .map((b) => (
            <rect
              key={b.id}
              x={x(numeric(b.start) ?? 0) - 6}
              y="16"
              width={Math.max(
                12,
                x(numeric(b.end) ?? 0) - x(numeric(b.start) ?? 0),
              )}
              height={height - 50}
              fill="var(--ivory)"
              fillOpacity=".035"
            />
          ))}
        {session.bins
          .filter((b) => !b.sampled)
          .map((b) => (
            <g key={b.id}>
              <title>
                Not sampled. We have no measurements for this stretch.
              </title>
              <rect
                x={x(numeric(b.start) ?? 0)}
                y="12"
                width={Math.max(
                  0,
                  x(numeric(b.end) ?? 0) - x(numeric(b.start) ?? 0),
                )}
                height={height - 40}
                fill={`url(#hatch-${id})`}
              />
            </g>
          ))}
        {session.threshold &&
          numeric(session.threshold.value) !== undefined && (
            <g>
              <line
                x1="18"
                x2={width - 18}
                y1={y(numeric(session.threshold.value)!)}
                y2={y(numeric(session.threshold.value)!)}
                className="threshold"
              />
              <text x="20" y={y(numeric(session.threshold.value)!) - 6}>
                {session.threshold.label}
              </text>
            </g>
          )}
        {runs.map((run, i) => (
          <LinePath
            key={i}
            data={run}
            x={(b) => x(numeric(b.start) ?? 0)}
            y={(b) => y(numeric(b.median)!)}
            stroke="var(--ivory)"
            strokeWidth={1.75}
            fill="none"
            data-testid="condition-run"
          />
        ))}
        {session.bins
          .filter((b) => b.sampled && numeric(b.median) !== undefined)
          .map((b) => (
            <g
              key={b.id}
              role="button"
              tabIndex={0}
              aria-label={`Select ${b.id}`}
              onClick={() => select(b.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  select(b.id);
                }
              }}
            >
              <circle
                cx={x(numeric(b.start) ?? 0)}
                cy={y(numeric(b.median)!)}
                r="13"
                fill="transparent"
              />
              {b.severe ? (
                <path
                  d={`M ${x(numeric(b.start) ?? 0)} ${y(numeric(b.median)!) - 6} l 6 6 -6 6 -6 -6 Z`}
                  className="defect-dot"
                />
              ) : selected === b.id ? (
                <circle
                  cx={x(numeric(b.start) ?? 0)}
                  cy={y(numeric(b.median)!)}
                  r="5"
                  fill="var(--teal)"
                />
              ) : null}
            </g>
          ))}
        <text x="34" y={height - 3}>
          0 m
        </text>
        <text x={width - 14} y={height - 3} textAnchor="end">
          {numeric(session.length) ?? "Unknown"} m
        </text>
      </svg>
      <div className="chart-legend">
        <span>
          <i className="legend-line" />
          Sampled strip
        </span>
        <span>
          <i className="hatch-swatch" />
          Not sampled
        </span>
      </div>
      {table && (
        <div className="table-scroll">
          <table>
            <caption>Condition by route distance</caption>
            <thead>
              <tr>
                <th>Bin</th>
                <th>Distance</th>
                <th>Index</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {session.bins.map((b) => (
                <tr key={b.id}>
                  <td>{b.id}</td>
                  <td>
                    <MetricValue metric={b.start} />
                  </td>
                  <td>
                    <MetricValue metric={b.median} />
                  </td>
                  <td>{b.sampled ? "Sampled" : "Not sampled"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
