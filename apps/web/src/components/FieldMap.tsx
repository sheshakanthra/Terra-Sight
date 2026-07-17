"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import "maplibre-gl/dist/maplibre-gl.css";

import type { Bounds, Field, NdviOverlay, PolygonGeometry } from "@/lib/types";

/** Thanjavur delta — dense smallholder cropland, and a sane place to land. */
const INITIAL_CENTER: [number, number] = [79.13, 10.79];
const INITIAL_ZOOM = 13;

const FIELDS_SOURCE = "saved-fields";
const OVERLAY_SOURCE = "ndvi-overlay";
const OVERLAY_LAYER = "ndvi-overlay-layer";

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
  overlay: NdviOverlay | null;
  /** When set, the map flies to frame this extent (west, south, east, north). */
  focusBounds?: Bounds | null;
  onPolygonDrawn: (geometry: PolygonGeometry) => void;
}

export default function FieldMap({
  fields,
  drawing,
  overlay,
  focusBounds,
  onPolygonDrawn,
}: FieldMapProps) {
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

  // Pin the NDVI overlay image to its geographic bounds. Re-added on change
  // because an image source's coordinates are fixed at creation.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;

    if (instance.getLayer(OVERLAY_LAYER)) instance.removeLayer(OVERLAY_LAYER);
    if (instance.getSource(OVERLAY_SOURCE)) instance.removeSource(OVERLAY_SOURCE);
    if (!overlay) return;

    const [west, south, east, north] = overlay.bounds;
    instance.addSource(OVERLAY_SOURCE, {
      type: "image",
      url: overlay.url,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    });
    // Drawn above the field outline so the health colours read clearly.
    instance.addLayer({
      id: OVERLAY_LAYER,
      type: "raster",
      source: OVERLAY_SOURCE,
      paint: { "raster-opacity": 0.85, "raster-resampling": "nearest" },
    });
  }, [overlay, ready]);

  // Frame the selected field when asked.
  useEffect(() => {
    if (!ready || !map.current || !focusBounds) return;
    const [west, south, east, north] = focusBounds;
    map.current.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 48, duration: 600, maxZoom: 16 },
    );
  }, [focusBounds, ready]);

  // Toggle drawing. "static" is terra-draw's inert mode: the map still pans,
  // but clicks no longer start a polygon.
  useEffect(() => {
    if (!ready || !draw.current) return;
    draw.current.setMode(drawing ? "polygon" : "static");
    if (!drawing) draw.current.clear();
  }, [drawing, ready]);

  return <div ref={container} className="h-full w-full" />;
}
