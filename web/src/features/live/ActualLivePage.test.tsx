import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ActualLivePage from "./ActualLivePage";
import { createLiveSession, finishSession, sendFrame, readSession } from "../../api/real-assessment";

vi.mock("../../api/real-assessment", () => ({
  createLiveSession: vi.fn(async () => ({ session_id: "live-1", status: "live", frame_count: 0, processed_count: 0, rejected_count: 0, dropped_count: 0 })),
  readSession: vi.fn(async () => ({ session_id: "live-1", status: "live", frame_count: 0, processed_count: 0, rejected_count: 0, dropped_count: 0 })),
  sendFrame: vi.fn(async () => ({ session_id: "live-1", status: "live", frame_count: 1, processed_count: 0, rejected_count: 0, dropped_count: 0 })),
  finishSession: vi.fn(async () => ({ session_id: "live-1", status: "finished", frame_count: 1, processed_count: 1, rejected_count: 0, dropped_count: 0 })),
}));
beforeEach(() => vi.clearAllMocks());
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

test("permission denial never creates a capture session", async () => {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(new Error("Permission denied")) } });
  render(<MemoryRouter><ActualLivePage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Start camera" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Permission denied");
  expect(createLiveSession).not.toHaveBeenCalled();
});

test("camera frames reach the API and leaving the page releases the camera", async () => {
  const stop = vi.fn();
  const track = { stop, label: "Test camera" };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] }) } });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["captured"], { type: "image/jpeg" })));
  const view = render(<MemoryRouter><ActualLivePage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Start camera" }));
  await waitFor(() => expect(createLiveSession).toHaveBeenCalled());
  const preview = screen.getByLabelText("Live camera preview");
  Object.defineProperties(preview, { videoWidth: { value: 640 }, videoHeight: { value: 480 } });
  fireEvent.loadedMetadata(preview);
  await waitFor(() => expect(sendFrame).toHaveBeenCalledOnce());
  expect(sendFrame).toHaveBeenCalledWith("live-1", expect.any(Blob), expect.any(String), expect.any(AbortSignal));
  view.unmount();
  expect(stop).toHaveBeenCalled();
  expect(finishSession).toHaveBeenCalledWith("live-1");
});

test("capture waits for an outstanding frame instead of flooding the queue", async () => {
  vi.useFakeTimers();
  const track = { stop: vi.fn(), label: "Test camera" };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] }) } });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["frame"], { type: "image/jpeg" })));
  vi.mocked(readSession).mockResolvedValue({ session_id: "live-1", status: "live", mode: "live", created_at: "2026-10-16", frame_count: 1, processed_count: 0, rejected_count: 0, dropped_count: 0, is_stale: false });
  const view = render(<MemoryRouter><ActualLivePage /></MemoryRouter>);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start camera" })); });
  const preview = screen.getByLabelText("Live camera preview");
  Object.defineProperties(preview, { videoWidth: { value: 640 }, videoHeight: { value: 480 } });
  await act(async () => { fireEvent.loadedMetadata(preview); });
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(sendFrame).not.toHaveBeenCalled();
  view.unmount();
});
