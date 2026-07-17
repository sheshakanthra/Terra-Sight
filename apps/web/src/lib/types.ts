export interface PolygonGeometry {
  type: "Polygon";
  coordinates: number[][][];
}

export interface Field {
  id: string;
  name: string;
  area_ha: number;
  created_at: string;
  geometry: PolygonGeometry;
}

/** (west, south, east, north) in EPSG:4326 — the extent to pin an overlay to. */
export type Bounds = [number, number, number, number];

export interface ObservationSummary {
  date: string;
  scene_id: string;
  valid_pct: number;
  median_ndvi: number;
  overlay_url: string;
  bounds_wgs84: Bounds;
}

export interface RefreshResult {
  scenes_found: number;
  dates_processed: number;
  valid_dates: number;
  active_alerts: number;
  observations: ObservationSummary[];
}

export interface NdviOverlay {
  url: string;
  bounds: Bounds;
}

export interface ZoneStats {
  mean: number;
  median: number;
  p10: number;
  p90: number;
  n_pixels: number;
}

export interface ZoneCell {
  row: number;
  col: number;
  valid_pct: number;
  stats: ZoneStats | null;
}

export interface Observation {
  date: string;
  scene_id: string;
  valid_pct: number;
  stats: ZoneStats;
  zonal: ZoneCell[];
  overlay_url: string | null;
  bounds: Bounds | null;
}

export type AlertType = "field_decline" | "zone_decline";
export type Severity = "low" | "medium" | "high";

export interface Alert {
  zone: string;
  type: AlertType;
  severity: Severity;
  evidence: Record<string, number | string | boolean>;
  created_at: string;
  updated_at: string;
}

export interface Weather {
  rain_next_7d_mm: number;
  rain_past_14d_mm: number;
}

export interface AdviceItem {
  priority: number;
  action: string;
  reason: string;
  evidence_refs: string[];
}

export interface Advice {
  source: "llm" | "template";
  crop: string | null;
  items: AdviceItem[];
}
