import { create } from "zustand";
interface Selection {
  binId: string | null;
  selectBin: (id: string | null) => void;
  layers: { bins: boolean; points: boolean; accuracy: boolean };
  toggleLayer: (id: "bins" | "points" | "accuracy") => void;
}
export const useSelection = create<Selection>((set) => ({
  binId: null,
  selectBin: (binId) => set({ binId }),
  layers: { bins: true, points: false, accuracy: false },
  toggleLayer: (id) =>
    set((s) => ({ layers: { ...s.layers, [id]: !s.layers[id] } })),
}));
