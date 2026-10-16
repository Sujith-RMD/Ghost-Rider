import { beforeEach, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssessPage from "./AssessPage";

vi.mock("../../api/real-assessment", () => ({
  apiBase: "http://127.0.0.1:8000",
  readJob: vi.fn(async () => ({ job_id: "job-1", status: "partial", result_sample_id: "sample-1", error_reason: null })),
  readSample: vi.fn(async () => ({
    sample_id: "sample-1", image_url: "/uploads/road.jpg", quality: { status: "accepted", reasons: [] },
    score: null, geometry_valid: false, metrics: { chip_count: 0, chip_density_per_m2: null },
    error: null, model_version: "measure-v1",
  })),
  startAssessment: vi.fn(),
}));

beforeEach(() => sessionStorage.clear());

test("a resumed partial job shows real zero separately from unavailable score and density", async () => {
  sessionStorage.setItem("roadsight.activeJob", "job-1");
  render(<MemoryRouter><AssessPage mock={false} /></MemoryRouter>);
  expect(await screen.findByText(/Road score: Unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Watershed candidate regions (unverified): 0. May include non-road pixels.")).toBeInTheDocument();
  expect(screen.getByText("Count per m²: Unavailable without calibrated area")).toBeInTheDocument();
  expect(screen.getByAltText("Original uploaded road image")).toHaveAttribute("src", "http://127.0.0.1:8000/uploads/road.jpg");
});
