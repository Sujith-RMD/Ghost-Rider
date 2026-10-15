/// <reference types="vite/client" />
declare module "virtual:roadsight-data" {
  export const DevFixturePanel: import("react").ComponentType<{
    state: import("./api/display").JobState;
    onChange: (state: import("./api/display").JobState) => void;
  }>;
  export const dataSource: import("./api/display").DataSource;
  export const PreviewBanner: () => import("react").ReactNode;
}
