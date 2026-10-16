import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { rememberSample } from "../api/recent-samples";

vi.mock("../api/real-assessment", () => ({
  readSample: vi.fn(async (id: string) => ({ sample_id: id, quality: { status: "accepted" }, score: null })),
}));

vi.mock("virtual:roadsight-data", () => ({
  dataSource: {
    mock: false,
    load: async () => { throw new Error("Fixture workspace unavailable"); },
  },
  PreviewBanner: () => null,
}));

it("opens the connected assessment instead of the stale contract error", async () => {
  vi.stubGlobal("scrollTo", vi.fn());
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("heading", { name: "Assess a surface" })).toBeVisible();
  expect(screen.queryByText("Backend contract pending")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Route map" })).not.toBeInTheDocument();
});

it("shows real saved sample links instead of the disconnected screen", async () => {
  vi.stubGlobal("scrollTo", vi.fn());
  localStorage.clear();
  rememberSample("sample-123");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/samples"]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("link", { name: /Sample sample-123/ })).toHaveAttribute("href", "/samples/sample-123");
  expect(screen.queryByText("This screen is not connected yet")).not.toBeInTheDocument();
  localStorage.clear();
});
