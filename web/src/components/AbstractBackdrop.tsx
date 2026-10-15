import { useId } from "react";

// Mathematical linework only. No elevations, coordinates or geographic features.
const contours = Array.from({ length: 32 }, (_, level) => {
  const radius = 65 + level * 28;
  const points = Array.from({ length: 161 }, (_, i) => {
    const angle = (i / 160) * Math.PI * 2;
    const ripple =
      1 +
      0.12 * Math.sin(angle * 3 + 0.5) +
      0.07 * Math.cos(angle * 5 - level * 0.07);
    const x =
      1050 + Math.cos(angle) * radius * 1.4 * ripple + Math.sin(angle * 2) * 58;
    const y = 420 + Math.sin(angle) * radius * 0.87 * ripple;
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return points.join(" ") + " Z";
});
export function AbstractBackdrop({ compact = false }: { compact?: boolean }) {
  const id = useId().replaceAll(":", "");
  return (
    <div
      className={`abstract-backdrop ${compact ? "compact" : ""}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 1480 1080" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id={`contour-vignette-${id}`}>
            <stop offset="0" stopColor="#031211" stopOpacity="0" />
            <stop offset="1" stopColor="#031211" stopOpacity=".84" />
          </radialGradient>
        </defs>
        <g fill="none" stroke="#E8E4D3" strokeOpacity=".065" strokeWidth="1.2">
          {contours.map((d, i) => (
            <path d={d} key={i} />
          ))}
        </g>
        <rect
          width="1480"
          height="1080"
          fill={`url(#contour-vignette-${id})`}
        />
      </svg>
    </div>
  );
}
