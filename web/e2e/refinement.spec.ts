import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
test("reference refinement captures at the confirmed 1920 x 1080 desktop size", async ({
  page,
}) => {
  const folder = path.resolve("../docs/frontend/screenshots/refinement");
  await mkdir(folder, { recursive: true });
  const cases = [
    ["route-simulated", "/?fixture=simulated"],
    ["route-no-gps", "/?fixture=no-gps"],
    ["assess-idle", "/assess"],
    ["assess-selected", "/assess"],
    ["sample", "/samples/sample-01"],
    ["live", "/live"],
  ] as const;
  for (const [name, url] of cases) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(async () => { await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined))); });
    if (name === "assess-selected")
      await page
        .getByLabel("Choose road image")
        .setInputFiles(path.resolve("public/fixtures/road-placeholder.png"));
    if (name === "route-simulated") {
      await expect(
        page.getByText("Simulated route", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("Abstract backdrop, not a map", { exact: true }),
      ).toBeVisible();
    }
    if (name === "route-no-gps") {
      await expect(
        page.getByText(
          "This session has no GPS fix, so condition is shown by distance only.",
        ),
      ).toBeVisible();
      await expect(
        page.getByText("Simulated route", { exact: true }),
      ).toHaveCount(0);
    }
    if (name.startsWith("assess")) {
      await expect(
        page.getByRole("heading", { name: "Preview processing states" }),
      ).toHaveCount(0);
      await expect(page.locator("select")).toHaveCount(0);
      await expect(page.locator(".dev-fixture-panel")).toHaveCount(0);
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(
      result.violations,
      JSON.stringify(result.violations, null, 2),
    ).toEqual([]);
    await page.screenshot({
      path: path.join(folder, `${name}-1920x1080.png`),
      fullPage: false,
      animations: "disabled",
    });
  }
});

