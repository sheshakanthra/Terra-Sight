"use client";

import { useState } from "react";

import { severityColor, severityLabel } from "@/lib/ndvi";
import type { Advice, Alert } from "@/lib/types";
import { ZONE_NAMES } from "@/lib/zones";

function alertByRef(alerts: Alert[], ref: string): Alert | undefined {
  return alerts.find((a) => `${a.type}:${a.zone}` === ref);
}

function EvidenceChips({ alert }: { alert: Alert }) {
  const ev = alert.evidence;
  const chips: string[] = [];
  if (typeof ev.decline_pct === "number") chips.push(`↓ ${ev.decline_pct}%`);
  if (typeof ev.start_ndvi === "number" && typeof ev.end_ndvi === "number") {
    chips.push(`NDVI ${(ev.start_ndvi as number).toFixed(2)} → ${(ev.end_ndvi as number).toFixed(2)}`);
  }
  if (typeof ev.window_days === "number") chips.push(`${ev.window_days} days`);
  if (typeof ev.rain_next_7d_mm === "number") chips.push(`${ev.rain_next_7d_mm} mm rain / 7d`);
  if (ev.likely_water_stress) chips.push("likely water stress");

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <span
        className="rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
        style={{ color: severityColor(alert.severity), borderColor: severityColor(alert.severity) }}
      >
        {ZONE_NAMES[alert.zone] ?? alert.zone} · {severityLabel(alert.severity)}
      </span>
      {chips.map((chip) => (
        <span
          key={chip}
          className="rounded bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted tabular-nums"
        >
          {chip}
        </span>
      ))}
    </div>
  );
}

interface AdvicePanelProps {
  advice: Advice | null;
  alerts: Alert[];
  loading: boolean;
  onGenerate: () => void;
}

export default function AdvicePanel({ advice, alerts, loading, onGenerate }: AdvicePanelProps) {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="readout">What to do</span>
        {advice && (
          <span className="readout" title="How this advice was written">
            {advice.source === "llm" ? "AI-phrased" : "rule-based"}
          </span>
        )}
      </div>

      {!advice ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-muted">
            {alerts.length === 0
              ? "No stress detected in the latest passes."
              : `${alerts.length} active alert${alerts.length === 1 ? "" : "s"} on this field.`}
          </p>
          <button
            onClick={onGenerate}
            disabled={loading}
            className="rounded-md bg-healthy px-3 py-2 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Reading the evidence…" : "Get advice"}
          </button>
        </div>
      ) : (
        <ol className="flex flex-col gap-2">
          {advice.items.map((item, index) => {
            const isOpen = open === index;
            const citedAlerts = item.evidence_refs
              .map((ref) => alertByRef(alerts, ref))
              .filter((a): a is Alert => a !== undefined);
            return (
              <li key={index} className="rounded-md border border-border bg-background">
                <button
                  onClick={() => setOpen(isOpen ? null : index)}
                  className="flex w-full items-start gap-3 px-3 py-2.5 text-left"
                  aria-expanded={isOpen}
                >
                  <span className="mt-0.5 font-mono text-xs text-muted tabular-nums">
                    {item.priority}
                  </span>
                  <span className="flex-1 text-sm">{item.action}</span>
                  <span className="mt-0.5 text-muted">{isOpen ? "–" : "+"}</span>
                </button>
                {isOpen && (
                  <div className="border-t border-border px-3 py-2.5 pl-9">
                    <p className="text-sm text-muted">{item.reason}</p>
                    {citedAlerts.map((alert) => (
                      <EvidenceChips key={`${alert.type}:${alert.zone}`} alert={alert} />
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
