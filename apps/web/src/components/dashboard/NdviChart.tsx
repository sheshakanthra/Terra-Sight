"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Observation } from "@/lib/types";

interface NdviChartProps {
  observations: Observation[];
  activeDate: string | null;
}

interface Point {
  date: string;
  label: string;
  ndvi: number;
  p10: number;
  p90: number;
}

function label(dateStr: string): string {
  return new Date(dateStr + "T00:00:00Z").toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

export default function NdviChart({ observations, activeDate }: NdviChartProps) {
  const data: Point[] = [...observations]
    .reverse()
    .map((o) => ({
      date: o.date,
      label: label(o.date),
      ndvi: Number(o.stats.median.toFixed(3)),
      p10: Number(o.stats.p10.toFixed(3)),
      p90: Number(o.stats.p90.toFixed(3)),
    }));

  const active = data.find((d) => d.date === activeDate);

  return (
    <div className="panel p-4">
      <span className="readout">Field NDVI over time</span>
      <div className="mt-3 h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--color-muted)", fontSize: 10, fontFamily: "var(--font-mono)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border)" }}
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tick={{ fill: "var(--color-muted)", fontSize: 10, fontFamily: "var(--font-mono)" }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--color-muted)" }}
              formatter={(value, name) => [
                typeof value === "number" ? value.toFixed(2) : String(value),
                String(name).toUpperCase(),
              ]}
            />
            <Line
              type="monotone"
              dataKey="p90"
              stroke="var(--color-border)"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="p10"
              stroke="var(--color-border)"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="ndvi"
              stroke="var(--color-healthy)"
              strokeWidth={2}
              dot={{ r: 2.5, fill: "var(--color-healthy)" }}
              isAnimationActive={false}
            />
            {active && (
              <ReferenceDot
                x={active.label}
                y={active.ndvi}
                r={5}
                fill="var(--color-foreground)"
                stroke="var(--color-background)"
                strokeWidth={2}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="readout mt-2">Median NDVI · faint lines are the 10th–90th percentile spread</p>
    </div>
  );
}
