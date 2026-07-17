import type { Observation } from "@/lib/types";

/** 3x3 zone labels, north-up and row-major (matches the API). */
export const ZONE_GRID: string[][] = [
  ["NW", "N", "NE"],
  ["W", "C", "E"],
  ["SW", "S", "SE"],
];

export const ZONE_NAMES: Record<string, string> = {
  field: "Whole field",
  NW: "North-west",
  N: "North",
  NE: "North-east",
  W: "West",
  C: "Centre",
  E: "East",
  SW: "South-west",
  S: "South",
  SE: "South-east",
};

function zoneMedian(obs: Observation, row: number, col: number): number | null {
  const cell = obs.zonal.find((z) => z.row === row && z.col === col);
  return cell?.stats?.median ?? null;
}

export interface ZoneReading {
  label: string;
  row: number;
  col: number;
  current: number | null;
  /** Relative change (fraction) from the earliest to latest valid reading. */
  delta: number | null;
}

/**
 * Per-zone current NDVI and trend, from oldest→newest observations.
 * `current` is taken from `activeObs`; the trend spans all observations where
 * the zone had valid pixels.
 */
export function zoneReadings(
  observations: Observation[],
  activeObs: Observation | null,
): ZoneReading[] {
  const chronological = [...observations].sort((a, b) => a.date.localeCompare(b.date));
  const readings: ZoneReading[] = [];

  for (let row = 0; row < 3; row++) {
    for (let col = 0; col < 3; col++) {
      const series = chronological
        .map((o) => zoneMedian(o, row, col))
        .filter((v): v is number => v !== null);

      let delta: number | null = null;
      if (series.length >= 2 && series[0] > 0) {
        delta = (series[series.length - 1] - series[0]) / series[0];
      }

      readings.push({
        label: ZONE_GRID[row][col],
        row,
        col,
        current: activeObs ? zoneMedian(activeObs, row, col) : null,
        delta,
      });
    }
  }
  return readings;
}
