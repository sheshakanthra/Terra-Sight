"""Server-side validation and measurement of user-supplied field polygons.

Nothing here trusts the client. The browser sends GeoJSON; this module decides
whether it is a real, sane field polygon and how large it actually is. Every
rejection carries a message a farmer could read.
"""

import math
from typing import Any, Final

from pyproj import CRS, Transformer
from shapely.geometry import Polygon, shape
from shapely.ops import transform

MIN_AREA_HA: Final = 0.5
MAX_AREA_HA: Final = 500.0

_SQUARE_METRES_PER_HECTARE: Final = 10_000.0
_MIN_EXTERIOR_POSITIONS: Final = 4  # a closed triangle: 3 corners + repeat
_WGS84: Final = CRS.from_epsg(4326)


class GeometryError(ValueError):
    """User-supplied geometry was rejected. The message is farmer-facing."""


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the UTM zone containing this point.

    Areas must be measured in metres, not degrees — a degree of longitude is
    ~111 km at the equator and 0 km at the poles, so measuring in EPSG:4326
    would be meaningless. UTM is accurate enough at field scale.
    """
    zone = math.floor((lon + 180.0) / 6.0) + 1
    zone = min(max(zone, 1), 60)  # lon == 180 would otherwise yield zone 61
    return (32600 if lat >= 0 else 32700) + zone


def polygon_area_ha(polygon: Polygon) -> float:
    """Area in hectares, measured in the polygon's local UTM projection."""
    centroid = polygon.centroid
    utm = CRS.from_epsg(utm_epsg_for(centroid.x, centroid.y))
    to_utm = Transformer.from_crs(_WGS84, utm, always_xy=True).transform
    return float(transform(to_utm, polygon).area) / _SQUARE_METRES_PER_HECTARE


def _check_position(position: Any, ring_label: str) -> None:
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise GeometryError(f"The {ring_label} has a corner that is not a coordinate pair.")

    lon, lat = position[0], position[1]
    for value in (lon, lat):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GeometryError(f"The {ring_label} has a corner that is not a number.")
        if not math.isfinite(value):
            raise GeometryError(f"The {ring_label} has a corner that is not a real location.")

    if not -180.0 <= lon <= 180.0:
        raise GeometryError(
            "A corner sits outside the map (longitude must be between -180 and 180)."
        )
    if not -90.0 <= lat <= 90.0:
        raise GeometryError(
            "A corner sits outside the map (latitude must be between -90 and 90)."
        )


def _check_ring(ring: Any, ring_label: str) -> None:
    if not isinstance(ring, (list, tuple)):
        raise GeometryError(f"The {ring_label} is not a list of corners.")
    if len(ring) < _MIN_EXTERIOR_POSITIONS:
        raise GeometryError(
            f"The {ring_label} needs at least three corners to enclose any land."
        )

    for position in ring:
        _check_position(position, ring_label)

    first, last = ring[0], ring[-1]
    if (first[0], first[1]) != (last[0], last[1]):
        raise GeometryError(
            f"The {ring_label} does not close — its last corner must repeat the first."
        )


def validate_polygon(geojson: Any) -> Polygon:
    """Validate a GeoJSON Polygon and return it as a shapely geometry.

    Raises GeometryError with a friendly message on anything unusable.
    """
    if not isinstance(geojson, dict):
        raise GeometryError("The field outline is missing.")

    geom_type = geojson.get("type")
    if geom_type != "Polygon":
        raise GeometryError(
            f"A field must be a single polygon, not {geom_type or 'an unknown shape'}."
        )

    rings = geojson.get("coordinates")
    if not isinstance(rings, (list, tuple)) or not rings:
        raise GeometryError("The field outline has no corners.")

    _check_ring(rings[0], "field outline")
    for hole in rings[1:]:
        _check_ring(hole, "hole in the field")

    try:
        geometry = shape({"type": "Polygon", "coordinates": rings})
    except (ValueError, TypeError, AttributeError) as exc:
        raise GeometryError("The field outline could not be read.") from exc

    if not isinstance(geometry, Polygon):
        raise GeometryError("A field must be a single polygon.")
    if geometry.is_empty:
        raise GeometryError("The field outline encloses no area.")
    if not geometry.is_valid:
        # shapely's reason is jargon ("Self-intersection[80.2 10.7]"); the cause
        # that actually matters to someone drawing on a map is crossed edges.
        raise GeometryError("The field outline crosses over itself. Please redraw it.")

    return geometry


def validate_and_measure(geojson: Any) -> tuple[Polygon, float]:
    """Validate a field polygon and return it with its area in hectares.

    Size limits are enforced here: below MIN_AREA_HA a Sentinel-2 pixel grid is
    too coarse to say anything useful, and above MAX_AREA_HA it is not a
    smallholding this product is built for.
    """
    polygon = validate_polygon(geojson)
    area_ha = polygon_area_ha(polygon)

    if area_ha < MIN_AREA_HA:
        raise GeometryError(
            f"That field is about {area_ha:.2f} ha. Fields smaller than "
            f"{MIN_AREA_HA} ha are too small to read from satellite — "
            "satellite pixels are 10 m across."
        )
    if area_ha > MAX_AREA_HA:
        raise GeometryError(
            f"That field is about {area_ha:.0f} ha. Please draw a single field "
            f"of {MAX_AREA_HA:.0f} ha or less."
        )

    return polygon, area_ha
