"use client";

import type { Weather } from "@/lib/types";

const DRY_MM = 5;

export default function WeatherStrip({ weather }: { weather: Weather | null }) {
  return (
    <div className="panel p-4">
      <span className="readout">Rainfall</span>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="flex items-baseline gap-1">
            <span className="font-mono text-2xl font-semibold tabular-nums">
              {weather ? weather.rain_past_14d_mm.toFixed(0) : "—"}
            </span>
            <span className="readout">mm</span>
          </div>
          <p className="readout mt-1">Past 14 days</p>
        </div>
        <div>
          <div className="flex items-baseline gap-1">
            <span
              className="font-mono text-2xl font-semibold tabular-nums"
              style={
                weather && weather.rain_next_7d_mm < DRY_MM
                  ? { color: "var(--color-watch)" }
                  : undefined
              }
            >
              {weather ? weather.rain_next_7d_mm.toFixed(0) : "—"}
            </span>
            <span className="readout">mm</span>
          </div>
          <p className="readout mt-1">Next 7 days</p>
        </div>
      </div>
      {weather && weather.rain_next_7d_mm < DRY_MM && (
        <p className="mt-3 text-xs" style={{ color: "var(--color-watch)" }}>
          Dry week ahead — declines are more likely to be water stress.
        </p>
      )}
    </div>
  );
}
