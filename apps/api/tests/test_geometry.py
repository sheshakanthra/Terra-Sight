"""Geometry validation and measurement.

Coordinates below sit in the Thanjavur delta, Tamil Nadu — real cropland, which
is what the acceptance criterion asks for.
"""

import math

import pytest
from shapely.geometry import Polygon

from app.geometry import (
    MAX_AREA_HA,
    MIN_AREA_HA,
    GeometryError,
    polygon_area_ha,
    utm_epsg_for,
    validate_and_measure,
    validate_polygon,
)

# Thanjavur delta, near Kumbakonam.
_LON = 79.13
_LAT = 10.79

# Degree deltas for one kilometre at this latitude.
_KM_LAT = 1.0 / 110.6
_KM_LON = 1.0 / (111.32 * math.cos(math.radians(_LAT)))


def square(side_km: float, lon: float = _LON, lat: float = _LAT) -> dict:
    """A closed, counter-clockwise square of roughly side_km on each edge."""
    dx = _KM_LON * side_km / 2
    dy = _KM_LAT * side_km / 2
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - dx, lat - dy],
                [lon + dx, lat - dy],
                [lon + dx, lat + dy],
                [lon - dx, lat + dy],
                [lon - dx, lat - dy],
            ]
        ],
    }


class TestUtmZone:
    def test_thanjavur_is_utm_44n(self) -> None:
        assert utm_epsg_for(_LON, _LAT) == 32644

    def test_southern_hemisphere_uses_the_southern_band(self) -> None:
        # Canterbury Plains, New Zealand.
        assert utm_epsg_for(171.7, -43.6) == 32759

    @pytest.mark.parametrize("lon", [-180.0, 180.0])
    def test_antimeridian_stays_within_zone_1_to_60(self, lon: float) -> None:
        zone = utm_epsg_for(lon, 0.0) - 32600
        assert 1 <= zone <= 60


class TestArea:
    def test_one_square_kilometre_is_about_100_hectares(self) -> None:
        area = polygon_area_ha(Polygon(square(1.0)["coordinates"][0]))
        assert area == pytest.approx(100.0, rel=0.02)

    def test_area_is_measured_in_metres_not_degrees(self) -> None:
        """A degree-space area would be ~8e-5 for this square, not ~100 ha."""
        assert polygon_area_ha(Polygon(square(1.0)["coordinates"][0])) > 50.0

    def test_the_same_field_measures_the_same_in_both_hemispheres(self) -> None:
        north = polygon_area_ha(Polygon(square(1.0, lon=171.7, lat=43.6)["coordinates"][0]))
        south = polygon_area_ha(Polygon(square(1.0, lon=171.7, lat=-43.6)["coordinates"][0]))
        assert north == pytest.approx(south, rel=0.01)


class TestValidPolygons:
    def test_a_real_field_is_accepted_and_measured(self) -> None:
        polygon, area_ha = validate_and_measure(square(0.5))

        assert polygon.is_valid
        assert area_ha == pytest.approx(25.0, rel=0.02)

    def test_a_polygon_with_a_hole_is_accepted(self) -> None:
        outline = square(1.0)
        hole = square(0.2)["coordinates"][0]
        outline["coordinates"].append(list(reversed(hole)))

        polygon, area_ha = validate_and_measure(outline)

        assert polygon.interiors
        assert area_ha == pytest.approx(96.0, rel=0.05)


class TestRejections:
    def test_an_unclosed_ring_is_rejected(self) -> None:
        unclosed = square(1.0)
        unclosed["coordinates"][0].pop()

        with pytest.raises(GeometryError, match="does not close"):
            validate_polygon(unclosed)

    def test_a_self_intersecting_bowtie_is_rejected(self) -> None:
        dx, dy = _KM_LON * 0.5, _KM_LAT * 0.5
        bowtie = {
            "type": "Polygon",
            "coordinates": [
                [
                    [_LON - dx, _LAT - dy],
                    [_LON + dx, _LAT + dy],
                    [_LON + dx, _LAT - dy],
                    [_LON - dx, _LAT + dy],
                    [_LON - dx, _LAT - dy],
                ]
            ],
        }

        with pytest.raises(GeometryError, match="crosses over itself"):
            validate_polygon(bowtie)

    def test_too_few_corners_is_rejected(self) -> None:
        with pytest.raises(GeometryError, match="at least three corners"):
            validate_polygon({"type": "Polygon", "coordinates": [[[_LON, _LAT], [_LON, _LAT]]]})

    @pytest.mark.parametrize(
        "geojson",
        [
            {"type": "Point", "coordinates": [_LON, _LAT]},
            {"type": "MultiPolygon", "coordinates": []},
            {"coordinates": []},
            {},
        ],
    )
    def test_non_polygon_geometry_is_rejected(self, geojson: dict) -> None:
        with pytest.raises(GeometryError):
            validate_polygon(geojson)

    @pytest.mark.parametrize("payload", [None, "POLYGON((0 0))", 42, []])
    def test_non_object_payloads_are_rejected(self, payload: object) -> None:
        with pytest.raises(GeometryError):
            validate_polygon(payload)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_coordinates_are_rejected(self, bad: float) -> None:
        broken = square(1.0)
        broken["coordinates"][0][0] = [bad, _LAT]

        with pytest.raises(GeometryError, match="not a real location"):
            validate_polygon(broken)

    def test_off_the_map_longitude_is_rejected(self) -> None:
        broken = square(1.0)
        broken["coordinates"][0][0] = [181.0, _LAT]

        with pytest.raises(GeometryError, match="outside the map"):
            validate_polygon(broken)

    def test_off_the_map_latitude_is_rejected(self) -> None:
        broken = square(1.0)
        broken["coordinates"][0][0] = [_LON, 91.0]

        with pytest.raises(GeometryError, match="outside the map"):
            validate_polygon(broken)

    @pytest.mark.parametrize("bad", ["79.13", None, True, {}])
    def test_non_numeric_coordinates_are_rejected(self, bad: object) -> None:
        broken = square(1.0)
        broken["coordinates"][0][0] = [bad, _LAT]

        with pytest.raises(GeometryError):
            validate_polygon(broken)


class TestSizeLimits:
    def test_a_field_below_the_minimum_is_rejected(self) -> None:
        with pytest.raises(GeometryError, match="too small to read from satellite"):
            validate_and_measure(square(0.05))  # 50 m square -> 0.25 ha

    def test_a_field_above_the_maximum_is_rejected(self) -> None:
        with pytest.raises(GeometryError, match=r"or less"):
            validate_and_measure(square(3.0))  # 900 ha

    def test_the_limits_bracket_a_typical_smallholding(self) -> None:
        _, area_ha = validate_and_measure(square(0.3))  # 9 ha

        assert MIN_AREA_HA < area_ha < MAX_AREA_HA

    def test_the_rejection_message_reports_the_measured_size(self) -> None:
        with pytest.raises(GeometryError) as excinfo:
            validate_and_measure(square(0.05))

        assert "0.2" in str(excinfo.value) or "0.3" in str(excinfo.value)
