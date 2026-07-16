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
  observations: ObservationSummary[];
}

export interface NdviOverlay {
  url: string;
  bounds: Bounds;
}
