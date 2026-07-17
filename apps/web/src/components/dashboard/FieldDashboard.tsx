"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  getAdvice,
  getWeather,
  listAlerts,
  listObservations,
  refreshField,
} from "@/lib/api";
import type { Advice, Alert, Bounds, Field, NdviOverlay, Observation, Weather } from "@/lib/types";
import AdvicePanel from "@/components/dashboard/AdvicePanel";
import DateScrubber from "@/components/dashboard/DateScrubber";
import HonestyBadge from "@/components/dashboard/HonestyBadge";
import NdviChart from "@/components/dashboard/NdviChart";
import WeatherStrip from "@/components/dashboard/WeatherStrip";
import ZoneGrid from "@/components/dashboard/ZoneGrid";

const FieldMap = dynamic(() => import("@/components/FieldMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-surface" />,
});

function fieldBounds(field: Field): Bounds {
  const ring = field.geometry.coordinates[0];
  const lons = ring.map((p) => p[0]);
  const lats = ring.map((p) => p[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

interface FieldDashboardProps {
  field: Field;
}

export default function FieldDashboard({ field }: FieldDashboardProps) {
  const [observations, setObservations] = useState<Observation[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [obs, als] = await Promise.all([listObservations(field.id), listAlerts(field.id)]);
      setObservations(obs);
      setAlerts(als);
      setActiveIndex(0);
      // Weather is best-effort; a failure here should not blank the dashboard.
      getWeather(field.id)
        .then(setWeather)
        .catch(() => setWeather(null));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "This field could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [field.id]);

  useEffect(() => {
    setAdvice(null);
    void load();
  }, [load]);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    setAdvice(null);
    try {
      await refreshField(field.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Refresh failed. Please try again.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleGetAdvice() {
    setAdviceLoading(true);
    try {
      setAdvice(await getAdvice(field.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Advice could not be prepared.");
    } finally {
      setAdviceLoading(false);
    }
  }

  const activeObs = observations[activeIndex] ?? null;
  const overlay: NdviOverlay | null =
    activeObs?.overlay_url && activeObs.bounds
      ? { url: activeObs.overlay_url, bounds: activeObs.bounds }
      : null;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{field.name}</h2>
          <p className="font-mono text-xs text-muted tabular-nums">{field.area_ha.toFixed(2)} ha</p>
        </div>
        <div className="flex items-center gap-4">
          <HonestyBadge observations={observations} />
          <button
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:border-healthy disabled:opacity-50"
          >
            {refreshing ? "Reading satellite…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <p className="mx-6 mt-4 rounded-md border border-stress/40 bg-stress/10 px-3 py-2 text-sm text-stress">
          {error}
        </p>
      )}

      {loading ? (
        <p className="px-6 py-8 text-sm text-muted">Loading field…</p>
      ) : observations.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-12 text-center">
          <p className="max-w-sm text-sm text-muted">
            No satellite reads yet. Refresh to pull the last 45 days of clear passes and build this
            field&apos;s health history.
          </p>
          <button
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="rounded-md bg-healthy px-4 py-2 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {refreshing ? "Reading satellite…" : "Read satellite passes"}
          </button>
        </div>
      ) : (
        <div className="grid gap-4 p-6 lg:grid-cols-3">
          <div className="flex flex-col gap-3 lg:col-span-2">
            <div className="h-[360px] overflow-hidden rounded-lg border border-border">
              <FieldMap
                fields={[field]}
                drawing={false}
                overlay={overlay}
                focusBounds={fieldBounds(field)}
                onPolygonDrawn={() => {}}
              />
            </div>
            <DateScrubber
              observations={observations}
              activeIndex={activeIndex}
              onSelect={setActiveIndex}
            />
          </div>

          <div className="flex flex-col gap-4">
            <WeatherStrip weather={weather} />
            <ZoneGrid observations={observations} activeObs={activeObs} />
          </div>

          <div className="lg:col-span-2">
            <NdviChart observations={observations} activeDate={activeObs?.date ?? null} />
          </div>
          <div>
            <AdvicePanel
              advice={advice}
              alerts={alerts}
              loading={adviceLoading}
              onGenerate={() => void handleGetAdvice()}
            />
          </div>
        </div>
      )}
    </div>
  );
}
