import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

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
