// @vitest-environment node
import { expect, it } from "vitest";
import { build } from "vite";
import { productionHonestyGuard } from "../../scripts/honesty-guard";
it("the real production bundler refuses a fixture entry", async () => {
  await expect(
    build({
      configFile: false,
      logLevel: "silent",
      plugins: [productionHonestyGuard(true)],
      build: {
        write: false,
        lib: {
          entry: "src/mocks/fixtures.ts",
          formats: ["es"],
          fileName: "forbidden-fixture",
        },
      },
    }),
  ).rejects.toThrow("Production blocked");
});
