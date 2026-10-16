import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { DistressDetectionOverlay } from "./DistressDetectionOverlay";

test("shows saved detection boxes and the model caveat on the source image", () => {
  render(
    <DistressDetectionOverlay
      imageUrl="/road.jpg"
      evidence={{
        status: "success",
        model_version: "rdd2022-india-yolov8n",
        model_sha256: "abc123",
        image_width: 120,
        image_height: 80,
        inference_ms: 12.5,
        confidence_threshold: 0.25,
        detections: [{
          class_id: 2,
          class_name: "longitudinal crack",
          confidence: 0.875,
          bbox_xyxy: [12.5, 15, 40, 52.5],
        }],
      }}
    />,
  );

  expect(screen.getByAltText("Original uploaded road image")).toHaveAttribute("src", "/road.jpg");
  expect(screen.getByText("longitudinal crack · 88%")).toBeInTheDocument();
  expect(screen.getByText(/Detection boxes show localization/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Distress detection boxes" })).toHaveAttribute("viewBox", "0 0 120 80");
});

test("shows a real no-detection outcome separately from missing weights", () => {
  render(
    <DistressDetectionOverlay
      imageUrl="/road.jpg"
      evidence={{ status: "success", image_width: 120, image_height: 80, confidence_threshold: 0.25, detections: [] }}
    />,
  );

  expect(screen.getByText("No distress boxes detected by the configured model.")).toBeInTheDocument();
});
