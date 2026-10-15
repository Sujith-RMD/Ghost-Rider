import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { productionHonestyGuard } from "./scripts/honesty-guard";
export default defineConfig(({ mode }) => {
  const demo = mode !== "production";
  return {
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "roadsight-data-boundary",
        resolveId(id) {
          return id === "virtual:roadsight-data"
            ? "\0roadsight-data"
            : undefined;
        },
        load(id) {
          if (id !== "\0roadsight-data") return;
          return demo
            ? 'export { dataSource } from "/src/mocks/fixtures.ts"; export { PreviewBanner } from "/src/mocks/PreviewBanner.tsx";' +
                (mode === "development"
                  ? 'export {default as DevFixturePanel} from "/src/components/DevFixturePanel.tsx";'
                  : "export const DevFixturePanel = () => null;")
            : 'export { dataSource } from "/src/api/disconnected.ts"; export const PreviewBanner = () => null; export const DevFixturePanel = () => null;';
        },
      },
      productionHonestyGuard(!demo),
    ],
    publicDir: demo ? "public" : false,
    server: { port: 5173, strictPort: true },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
