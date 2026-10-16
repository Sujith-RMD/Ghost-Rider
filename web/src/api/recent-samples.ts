const key = "roadsight.recentSamples";

export function recentSampleIds(): string[] {
  try {
    const ids: unknown = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function rememberSample(id: string): void {
  try {
    localStorage.setItem(key, JSON.stringify([id, ...recentSampleIds().filter((saved) => saved !== id)].slice(0, 50)));
  } catch { /* Browser storage may be disabled; the current result remains available. */ }
}
