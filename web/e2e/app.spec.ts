import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
const pages = [
  ["route", "/"],
  ["assess", "/assess"],
  ["live", "/live"],
  ["samples", "/samples"],
  ["sample", "/samples/sample-01"],
  ["session", "/sessions/session-demo"],
  ["reports", "/reports"],
  ["report", "/reports/report-demo"],
  ["system", "/system"],
] as const;
test("all desktop pages at the user target 1920 x 1080", async ({ page }) => {
  const folder = path.resolve("../docs/frontend/screenshots");
  await mkdir(folder, { recursive: true });
  for (const width of [1920]) {
    await page.setViewportSize({
      width,
      height: 1080,
    });
    for (const [name, url] of pages) {
      await page.goto(url);
      await expect(
        page.getByRole("heading", { level: 1 }).first(),
      ).toBeVisible();
      await expect(
        page.getByText("Mock data. Values are not measurements."),
      ).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(
        results.violations,
        JSON.stringify(results.violations, null, 2),
      ).toEqual([]);
      if (name === "sample") {
        const image = await page
          .locator(".image-transform > img")
          .boundingBox();
        const viewport = await page.locator(".image-viewport").boundingBox();
        expect(image!.x).toBeLessThan(viewport!.x + viewport!.width / 2);
        expect(image!.x + image!.width).toBeGreaterThan(
          viewport!.x + viewport!.width / 2,
        );
      }
      await page.screenshot({
        path: path.join(folder, `${name}-${width}.png`),
        fullPage: true,
      });
    }
  }
});
test("route gaps, selected bins and source filters remain inspectable", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Map unavailable" }),
  ).toBeVisible();
  await expect(page.locator(".condition-run")).toHaveCount(0);
  await expect(page.getByTestId("condition-run")).toHaveCount(2);
  await page
    .getByRole("button", { name: "bin-4: not sampled", exact: true })
    .click();
  await expect(page.locator(".selected-bin")).toContainText("Not sampled");
  await page.keyboard.press("Escape");
  await expect(page.locator(".selected-bin")).toHaveCount(0);
  await page
    .locator(".source-filters button")
    .filter({ hasText: "Still" })
    .click();
  await expect(page.locator(".sample-card")).toHaveCount(2);
  await page
    .getByRole("button", { name: "bin-6: review", exact: true })
    .click();
  await expect(page.locator(".selected-bin")).toContainText(
    "Provisional reference-deviation index",
  );
  await page.screenshot({
    path: path.resolve("../docs/frontend/screenshots/route-selected-1920.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Segment evidence/ }).click();
  await expect(page.locator(".segment-drawer")).toHaveClass(/expanded/);
  const before = await page.locator(".drawer-toggle").boundingBox();
  await page
    .locator(".segment-drawer > .table-scroll")
    .evaluate((el) => (el.scrollTop = 500));
  const after = await page.locator(".drawer-toggle").boundingBox();
  expect(after!.y).toBe(before!.y);
  await page.screenshot({
    path: path.resolve("../docs/frontend/screenshots/route-table-1920.png"),
    fullPage: true,
  });
});
test("keyboard controls, evidence dialog, reduced motion and greyscale", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/samples/sample-01");
  await page.getByRole("button", { name: "Open full-screen evidence" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("tab", { name: "Inclination", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tabpanel")).toContainText("No verified grade");
  await page.goto("/assess");
  await page.getByRole("button", { name: "UI fixtures", exact: true }).click();
  await page.getByRole("option", { name: "Queued", exact: true }).click();
  await expect(
    page.getByText("Uploaded. Analysis hasn't finished yet."),
  ).toBeVisible();
  await page.goto("/live");
  await expect(page.getByRole("status")).toContainText("Stale result");
  await page.goto("/reports/report-demo");
  await expect(
    page.getByText("Template summary", { exact: true }),
  ).toBeVisible();
  await page.goto("/");
  await page.addStyleTag({ content: "html{filter:grayscale(1)}" });
  await page.screenshot({
    path: path.resolve("../docs/frontend/screenshots/route-greyscale.png"),
    fullPage: true,
  });
});

test.skip("tablet sheet and narrow mobile remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "Peek", exact: true }).click();
  await expect(page.locator(".route-sidebar")).toHaveClass(/sheet-peek/);
  await page.getByRole("button", { name: "Full", exact: true }).click();
  await expect(page.locator(".route-sidebar")).toHaveClass(/sheet-full/);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  await page.screenshot({
    path: path.resolve("../docs/frontend/screenshots/route-1024.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/samples/sample-01");
  await expect(
    page.getByRole("heading", { name: "Surface evidence", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
