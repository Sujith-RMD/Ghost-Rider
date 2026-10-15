import { formatTimestamp } from "../lib/format";
import { SegmentTable } from "../components/SegmentTable";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  MetricValue,
  ConditionChip,
  SourceModeChip,
  JobStepper,
  ErrorPanel,
} from "../components/primitives";
import { measured, unknown, unsupported } from "../lib/metric";
import { workspace, bins } from "../mocks/fixtures";
import { RouteChart, conditionRuns } from "../components/RouteChart";
import { DistanceStrip } from "../features/route-map/RoutePage";
import { LiveMonitor } from "../features/live/LivePage";
import { ReportView } from "../features/report/ReportPage";
import { binStyle } from "../features/route-map/GoogleRouteMap";
import { isStale, jobPollingInterval } from "../lib/polling";
import { productionHonestyGuard } from "../../scripts/honesty-guard";
describe("scientific honesty", () => {
  it("1: measured zero and unknown have different visible output", () => {
    render(
      <>
        <MetricValue metric={measured(0, "m²")} />
        <MetricValue metric={unknown("No GPS fix")} />
      </>,
    );
    expect(screen.getByText("m²")).toBeVisible();
    expect(screen.getByText("0")).toBeVisible();
    expect(screen.getByText("—")).toBeVisible();
    expect(screen.getByText("No GPS fix")).toBeVisible();
  });
  it("2: null score cannot present a good condition or zero", () => {
    const { container } = render(
      <>
        <MetricValue metric={unknown("Missing evidence")} />
        <ConditionChip condition="good" score={unknown("Missing evidence")} />
      </>,
    );
    expect(screen.queryByText("Good")).not.toBeInTheDocument();
    expect(container.querySelector('[data-condition="unknown"]')).toBeTruthy();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("3: uncalibrated values use pixels only", () => {
    render(
      <MetricValue
        metric={{ kind: "uncalibrated", pixelValue: 12, unit: "px" }}
      />,
    );
    expect(screen.getByText("px")).toBeVisible();
    expect(screen.getByText("Pixels only")).toBeVisible();
    expect(screen.queryByText("mm")).not.toBeInTheDocument();
  });
  it("4: source chips distinguish all three modes", () => {
    const { container } = render(
      <>
        <SourceModeChip mode="live" />
        <SourceModeChip mode="replay" />
        <SourceModeChip mode="still" />
      </>,
    );
    expect(container.querySelector('[data-mode="replay"]')).not.toHaveClass(
      "live",
    );
    expect(screen.getByText("Still")).toBeVisible();
    expect(screen.getByText("Replay")).toBeVisible();
    expect(screen.getByText("Live")).toBeVisible();
  });
  it("5: no GPS has a distance-only presentation", () => {
    const { container } = render(<DistanceStrip session={workspace.session} />);
    expect(screen.getByText("Linear distance report")).toBeVisible();
    expect(container.querySelector("iframe")).toBeNull();
  });
  it.each(["partial", "failed", "queued"] as const)(
    "6: %s never says analysis succeeded",
    (state) => {
      render(<JobStepper state={state} reason="Missing evidence" />);
      expect(screen.queryByText("Analysis succeeded.")).not.toBeInTheDocument();
      expect(screen.getByText("Missing evidence")).toBeVisible();
    },
  );
  it("7: stale results are marked and retain backend times", () => {
    render(<LiveMonitor monitor={workspace.monitor} />);
    expect(screen.getByRole("status")).toHaveTextContent("Stale result");
    expect(
      screen.getByText(formatTimestamp(workspace.monitor.capturedAt)),
    ).toBeVisible();
    expect(isStale(true, null)).toBe(true);
    expect(
      isStale(
        false,
        "2026-10-15T00:00:00Z",
        1000,
        Date.parse("2026-10-15T00:00:02Z"),
      ),
    ).toBe(true);
  });
  it("8: chart splits at unsampled bins and map style stays neutral", () => {
    expect(conditionRuns(bins)).toHaveLength(2);
    const { container } = render(<RouteChart session={workspace.session} />);
    expect(
      container.querySelectorAll('[data-testid="condition-run"]'),
    ).toHaveLength(2);
    expect(binStyle(false, "good")).toEqual(binStyle(false, "bad"));
    expect(binStyle(false, "good").color).toBe("#E8E4D3");
  });
  it.each(["Key rejected", "Billing unavailable", "Network unavailable"])(
    "9: Maps %s is an integration error",
    (title) => {
      const { container } = render(
        <ErrorPanel family="integration" title={title} />,
      );
      expect(
        container.querySelector('[data-error-family="integration"]'),
      ).toBeTruthy();
      expect(
        container.querySelector('[data-error-family="analysis"]'),
      ).toBeNull();
    },
  );
  it("10: template and unresolved references are explicit; prose cannot change facts", () => {
    render(
      <MemoryRouter>
        <ReportView
          report={{ ...workspace.report, narrative: "99999 imaginary number" }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Template summary")).toBeVisible();
    expect(
      screen.getByText("Unverified reference: Missing evidence"),
    ).toBeVisible();
    expect(screen.getByText("500")).toBeVisible();
    expect(screen.getByText("99999 imaginary number")).toBeVisible();
  });
  it("11: unsupported inclination has no derived numeric value", () => {
    render(
      <MetricValue metric={unsupported("No verified grade for this sample")} />,
    );
    expect(screen.getByText("No verified grade for this sample")).toBeVisible();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it("12: conditions have distinct glyphs/text and patterns independent of hue", () => {
    const { container } = render(
      <>
        {(["good", "bad", "review", "unknown"] as const).map((c) => (
          <ConditionChip condition={c} key={c} />
        ))}
      </>,
    );
    const icons = [...container.querySelectorAll(".condition svg")].map(
      (e) => e.innerHTML,
    );
    expect(new Set(icons).size).toBe(4);
    expect(container.querySelector(".review")).toHaveTextContent("Review");
    expect(container.querySelector(".unknown")).toHaveTextContent("Unknown");
  });
  it("13: production bundling rejects fixture imports and banner", () => {
    const guard = productionHonestyGuard(true);
    const hook = guard.generateBundle;
    const fn = typeof hook === "function" ? hook : hook?.handler;
    const error = vi.fn(() => {
      throw Error("blocked");
    });
    for (const chunk of [
      { type: "chunk", modules: { "/src/mocks/fixtures.ts": {} }, code: "" },
      {
        type: "chunk",
        modules: {},
        code: "Showing mock data. Values are not measurements.",
      },
    ])
      expect(() =>
        fn?.call({ error } as never, {} as never, { chunk } as never, false),
      ).toThrow("blocked");
  });
  it("polling backs off, pauses while hidden and stops on terminal state", () => {
    expect(jobPollingInterval("queued", 0, 2000, false)).toBe(1000);
    expect(jobPollingInterval("processing", 0, 31000, false)).toBe(3000);
    expect(jobPollingInterval("processing", 0, 31000, true)).toBe(false);
    expect(jobPollingInterval("partial", 0, 31000, false)).toBe(false);
  });
});

it("virtualizes long segment tables without losing later bins", () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const many = Array.from({ length: 400 }, (_, i) => ({
    ...bins[0],
    id: `virtual-${i}`,
    start: measured(i * 50, "m"),
  }));
  const { container } = render(<SegmentTable bins={many} />);
  expect(container.querySelectorAll("tr[data-bin-id]").length).toBeLessThan(30);
  expect(screen.queryByText("virtual-180")).not.toBeInTheDocument();
  fireEvent.scroll(container.querySelector(".table-scroll")!, {
    target: { scrollTop: 20000 },
  });
  expect(screen.getByText("virtual-180")).toBeVisible();
  vi.unstubAllGlobals();
});
it("retains a small positive measurement instead of rounding it to zero", () => {
  render(<MetricValue metric={measured(0.006, "m²")} />);
  expect(screen.getByText("0")).toBeVisible();
  expect(screen.getByText(".006")).toBeVisible();
});

it("never paints a null-score bin with a good condition", () => {
  const session = {
    ...workspace.session,
    bins: [
      { ...bins[0], condition: "good" as const, median: unknown("No score") },
    ],
  };
  const { container } = render(<DistanceStrip session={session} />);
  expect(container.querySelector(".distance-bin")).toHaveClass("unknown");
  expect(container.querySelector(".distance-bin")).not.toHaveClass("good");
});
