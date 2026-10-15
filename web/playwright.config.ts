import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  outputDir: `test-results/run-${Date.now()}`,
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  reporter: [["list"], ["html", { open: "never", outputFolder: `playwright-report/run-${Date.now()}` }]],
  use: {
    baseURL: "http://127.0.0.1:5183",
    ...devices["Desktop Chrome"],
    viewport: {width: 1920, height: 1080},
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
  webServer: {
    command: "npm run dev -- --port 5183",
    url: "http://127.0.0.1:5183",
    reuseExistingServer: true,
    timeout: 60000,
  },
});
