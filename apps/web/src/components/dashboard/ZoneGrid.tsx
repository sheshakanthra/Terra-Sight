"use client";

import { ndviColor } from "@/lib/ndvi";
import type { Observation } from "@/lib/types";
import { zoneReadings } from "@/lib/zones";

/** Threshold below which a zone's change reads as a real move, not noise. */
const TREND_EPS = 0.03;

function TrendArrow({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-muted">·</span>;
  if (delta <= -TREND_EPS) return <span style={{ color: "var(--color-stress)" }}>↓</span>;
  if (delta >= TREND_EPS) return <span style={{ color: "var(--color-healthy)" }}>↑</span>;
  return <span className="text-muted">→</span>;
}

interface ZoneGridProps {
  observations: Observation[];
  activeObs: Observation | null;
}

/**
 * The field's 3x3 zones as a north-up health matrix: each cell filled by its
 * current NDVI, with a trend arrow. This is where "the north-west corner is
 * declining" becomes something you can see at a glance.
 */
export default function ZoneGrid({ observations, activeObs }: ZoneGridProps) {
  const readings = zoneReadings(observations, activeObs);

  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="readout">Zone health</span>
        <span className="readout" aria-hidden>
          N ↑
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {readings.map((zone) => {
          const filled = zone.current !== null;
          return (
            <div
              key={zone.label}
              className="relative flex aspect-square flex-col items-center justify-center rounded-md border border-border"
              style={
                filled
                  ? { backgroundColor: ndviColor(zone.current as number) }
                  : {
                      backgroundImage:
                        "repeating-linear-gradient(45deg, transparent, transparent 4px, var(--color-border) 4px, var(--color-border) 5px)",
                    }
              }
              title={
                filled
                  ? `${zone.label}: NDVI ${(zone.current as number).toFixed(2)}`
                  : `${zone.label}: no clear pixels`
              }
            >
              <span
                className="font-mono text-[10px] font-medium"
                style={{ color: filled ? "rgba(0,0,0,0.65)" : "var(--color-muted)" }}
              >
                {zone.label}
              </span>
              {filled ? (
                <span
                  className="font-mono text-sm font-semibold tabular-nums"
                  style={{ color: "rgba(0,0,0,0.8)" }}
                >
                  {(zone.current as number).toFixed(2)}
                </span>
              ) : (
                <span className="font-mono text-sm text-muted">—</span>
              )}
              <span className="absolute right-1 top-1 text-xs">
                <TrendArrow delta={zone.delta} />
              </span>
            </div>
          );
        })}
      </div>
      <p className="readout mt-3 leading-relaxed">Colour = NDVI · arrow = trend across passes</p>
    </div>
  );
}
