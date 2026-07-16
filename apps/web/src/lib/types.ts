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
