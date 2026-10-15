import type { Plugin } from "vite";
export function productionHonestyGuard(enabled: boolean): Plugin {
  return {
    name: "production-honesty-guard",
    generateBundle(_options, bundle) {
      if (!enabled) return;
      for (const asset of Object.values(bundle)) {
        if (asset.type !== "chunk") continue;
        if (
          Object.keys(asset.modules).some((id) =>
            /[\\/]src[\\/]mocks[\\/]/.test(id),
          ) ||
          asset.code.includes(
            "Showing mock data. Values are not measurements.",
          ) ||
          asset.code.includes("Mock data. Values are not measurements.") ||
          Object.keys(asset.modules).some((id) =>
            /[\\/]DevFixturePanel\.tsx$/.test(id),
          )
        )
          this.error(
            "Production blocked: mock data or the mock banner is included.",
          );
      }
    },
  };
}
