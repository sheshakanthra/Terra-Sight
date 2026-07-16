"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import "maplibre-gl/dist/maplibre-gl.css";

import type { Field, PolygonGeometry } from "@/lib/types";

/** Thanjavur delta — dense smallholder cropland, and a sane place to land. */
const INITIAL_CENTER: [number, number] = [79.13, 10.79];
const INITIAL_ZOOM = 13;

const FIELDS_SOURCE = "saved-fields";

/**
 * Satellite imagery, not a street map: field boundaries are invisible on a
 * road basemap, so you could not draw against anything real.
 */
const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "satellite", type: "raster", source: "satellite" }],
};

function toFeatureCollection(fields: Field[]) {
  return {
    type: "FeatureCollection" as const,
    features: fields.map((field) => ({
      type: "Feature" as const,
      id: field.id,
      properties: { name: field.name, area_ha: field.area_ha },
      geometry: field.geometry,
    })),
  };
}

interface FieldMapProps {
  fields: Field[];
  drawing: boolean;
  onPolygonDrawn: (geometry: PolygonGeometry) => void;
}

export default function FieldMap({ fields, drawing, onPolygonDrawn }: FieldMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const draw = useRef<TerraDraw | null>(null);
  // The map loads asynchronously. Without this gate, fields or a mode change
  // arriving before "load" would be dropped silently.
  const [ready, setReady] = useState(false);
  // Kept in a ref so the map effect never re-runs when the callback identity
  // changes — re-creating the map would tear down the user's drawing.
  const onPolygonDrawnRef = useRef(onPolygonDrawn);
  onPolygonDrawnRef.current = onPolygonDrawn;

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: SATELLITE_STYLE,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-right");
    map.current = instance;

    instance.on("load", () => {
      instance.addSource(FIELDS_SOURCE, { type: "geojson", data: toFeatureCollection([]) });
      instance.addLayer({
        id: "saved-fields-fill",
        type: "fill",
        source: FIELDS_SOURCE,
        paint: { "fill-color": "#3fb950", "fill-opacity": 0.18 },
      });
      instance.addLayer({
        id: "saved-fields-outline",
        type: "line",
        source: FIELDS_SOURCE,
        paint: { "line-color": "#3fb950", "line-width": 2 },
      });

      const terraDraw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map: instance }),
        modes: [new TerraDrawPolygonMode({ pointerDistance: 30 })],
      });
      terraDraw.start();
      terraDraw.setMode("static");
      terraDraw.on("finish", (id) => {
        const feature = terraDraw.getSnapshot().find((f) => f.id === id);
        if (feature?.geometry.type === "Polygon") {
          onPolygonDrawnRef.current(feature.geometry as PolygonGeometry);
        }
      });
      draw.current = terraDraw;
      setReady(true);
    });

    return () => {
      draw.current?.stop();
      draw.current = null;
      instance.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  // Push saved fields into the map whenever they change.
  useEffect(() => {
    if (!ready) return;
    const source = map.current?.getSource(FIELDS_SOURCE) as maplibregl.GeoJSONSource | undefined;
    source?.setData(toFeatureCollection(fields));
  }, [fields, ready]);

  // Toggle drawing. "static" is terra-draw's inert mode: the map still pans,
  // but clicks no longer start a polygon.
  useEffect(() => {
    if (!ready || !draw.current) return;
    draw.current.setMode(drawing ? "polygon" : "static");
    if (!drawing) draw.current.clear();
  }, [drawing, ready]);

  return <div ref={container} className="h-full w-full" />;
}
