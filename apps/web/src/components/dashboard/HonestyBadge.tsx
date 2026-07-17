"use client";

import type { Observation } from "@/lib/types";

function daysAgo(dateStr: string): number {
  const then = new Date(dateStr + "T00:00:00Z").getTime();
  const now = Date.now();
  return Math.max(0, Math.floor((now - then) / 86_400_000));
}

/**
 * The honesty badge. TerraSight only sees the ground through cloud gaps, so it
 * says plainly how stale the last clear pass is instead of implying it is live.
 */
export default function HonestyBadge({ observations }: { observations: Observation[] }) {
  const latest = observations[0]; // API returns newest-first
  if (!latest) {
    return (
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-muted" />
        <span className="readout">No clear pass yet</span>
      </div>
    );
  }

  const n = daysAgo(latest.date);
  const stale = n > 12;
  const color = stale ? "var(--color-watch)" : "var(--color-healthy)";

  return (
    <div className="flex items-center gap-2" title={`Latest clear scene: ${latest.date}`}>
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="readout" style={{ color }}>
        Last clear pass · {n === 0 ? "today" : `${n} day${n === 1 ? "" : "s"} ago`}
      </span>
    </div>
  );
}
