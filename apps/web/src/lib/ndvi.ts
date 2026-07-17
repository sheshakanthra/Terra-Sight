import type { Severity } from "@/lib/types";

/**
 * NDVI colour ramp — the same brown→green stops the API bakes into the PNG
 * overlay, so the zone grid and chart read as one instrument with the map.
 */
const STOPS: Array<[number, [number, number, number]]> = [
  [0.0, [140, 81, 10]],
  [0.2, [191, 129, 45]],
  [0.35, [223, 194, 125]],
  [0.5, [199, 234, 177]],
  [0.65, [127, 188, 65]],
  [0.8, [35, 132, 67]],
];

const NDVI_MIN = 0.0;
const NDVI_MAX = 0.8;

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Hex colour for an NDVI value, clamped to the ramp's [0, 0.8] range. */
export function ndviColor(value: number): string {
  const v = Math.min(Math.max(value, NDVI_MIN), NDVI_MAX);
  let lo = STOPS[0];
  let hi = STOPS[STOPS.length - 1];
  for (let i = 0; i < STOPS.length - 1; i++) {
    if (v >= STOPS[i][0] && v <= STOPS[i + 1][0]) {
      lo = STOPS[i];
      hi = STOPS[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  const t = (v - lo[0]) / span;
  const rgb = lo[1].map((c, i) => Math.round(lerp(c, hi[1][i], t)));
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

/** Semantic severity colour — reserved strictly for alert severity. */
export function severityColor(severity: Severity): string {
  return { low: "var(--color-watch)", medium: "var(--color-watch)", high: "var(--color-stress)" }[
    severity
  ];
}

export function severityLabel(severity: Severity): string {
  return { low: "Watch", medium: "Concern", high: "Stress" }[severity];
}
