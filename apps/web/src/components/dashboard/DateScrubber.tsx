"use client";

import { ndviColor } from "@/lib/ndvi";
import type { Observation } from "@/lib/types";

function shortDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00Z").toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

interface DateScrubberProps {
  observations: Observation[]; // newest-first
  activeIndex: number;
  onSelect: (index: number) => void;
}

/**
 * The clear passes as a film strip, oldest→newest. Each tick is a real
 * satellite date, tinted by that day's field NDVI; cloud gaps simply are not
 * here, which is the honest way to show them.
 */
export default function DateScrubber({ observations, activeIndex, onSelect }: DateScrubberProps) {
  const chronological = [...observations].reverse(); // oldest → newest for reading

  return (
    <div className="panel px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="readout">Clear passes</span>
        <span className="readout">{observations.length} in 45 days</span>
      </div>
      <div className="flex items-end gap-1.5 overflow-x-auto pb-1">
        {chronological.map((obs) => {
          // Map back to the newest-first index the parent works in.
          const idx = observations.findIndex((o) => o.date === obs.date);
          const active = idx === activeIndex;
          return (
            <button
              key={obs.date}
              onClick={() => onSelect(idx)}
              className="group flex shrink-0 flex-col items-center gap-1"
              aria-pressed={active}
              aria-label={`View ${obs.date}, NDVI ${obs.stats.median.toFixed(2)}`}
            >
              <span
                className="h-9 w-9 rounded-md border transition-transform group-hover:scale-105"
                style={{
                  backgroundColor: ndviColor(obs.stats.median),
                  borderColor: active ? "var(--color-foreground)" : "var(--color-border)",
                  borderWidth: active ? 2 : 1,
                }}
              />
              <span
                className="font-mono text-[10px] tabular-nums"
                style={{ color: active ? "var(--color-foreground)" : "var(--color-muted)" }}
              >
                {shortDate(obs.date)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
