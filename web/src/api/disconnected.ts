import type { DataSource } from "./display";
export const dataSource: DataSource = {
  mock: false,
  contractVersion: null,
  load: async () => {
    throw new Error(
      "The backend contract is not published. Real assessments are not connected yet.",
    );
  },
};
