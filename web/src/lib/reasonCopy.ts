export const reasonCopy: Record<string, string> = {
  blur: "The image is too blurred to measure. Try a slower pass or a faster shutter.",
  scale: "Scale not calibrated",
  gps: "No GPS fix",
  resolution: "Below the validated measurement limit",
  surface: "This image does not show a supported road surface.",
};
export const explainReason = (code: string) =>
  reasonCopy[code] ?? `Not supported yet: ${code}`;
