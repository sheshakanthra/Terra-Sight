"""Pure NDVI / masking / statistics — the scientifically load-bearing logic."""

import numpy as np
import pytest

from app.imagery.analysis import (
    MASKED_SCL_CLASSES,
    MIN_VALID_FRACTION,
    compute_ndvi,
    effective_mask,
    scl_valid_mask,
    summarize,
    valid_fraction,
    zonal_stats,
)


class TestNdvi:
    def test_ndvi_formula(self) -> None:
        red = np.array([[0.2]], dtype=np.float32)
        nir = np.array([[0.6]], dtype=np.float32)
        # (0.6 - 0.2) / (0.6 + 0.2) = 0.5
        assert compute_ndvi(red, nir)[0, 0] == pytest.approx(0.5)

    def test_ndvi_is_bounded_between_minus_one_and_one(self) -> None:
        rng = np.random.default_rng(0)
        red = rng.uniform(0, 5000, (32, 32)).astype(np.float32)
        nir = rng.uniform(0, 5000, (32, 32)).astype(np.float32)
        ndvi = compute_ndvi(red, nir)
        assert np.nanmin(ndvi) >= -1.0
        assert np.nanmax(ndvi) <= 1.0

    def test_zero_denominator_becomes_nan_not_zero(self) -> None:
        red = np.array([[0.0]], dtype=np.float32)
        nir = np.array([[0.0]], dtype=np.float32)
        assert np.isnan(compute_ndvi(red, nir)[0, 0])

    def test_healthy_vegetation_reads_high(self) -> None:
        red = np.full((4, 4), 600, dtype=np.float32)
        nir = np.full((4, 4), 3500, dtype=np.float32)
        assert compute_ndvi(red, nir).mean() > 0.6


class TestSclMask:
    @pytest.mark.parametrize("cls", sorted(MASKED_SCL_CLASSES))
    def test_masked_classes_are_excluded(self, cls: int) -> None:
        scl = np.array([[cls]], dtype=np.uint8)
        assert not scl_valid_mask(scl)[0, 0]

    @pytest.mark.parametrize("cls", [4, 5, 6, 7])
    def test_vegetation_soil_water_are_kept(self, cls: int) -> None:
        scl = np.array([[cls]], dtype=np.uint8)
        assert scl_valid_mask(scl)[0, 0]

    def test_the_masked_set_is_exactly_the_spec(self) -> None:
        assert MASKED_SCL_CLASSES == frozenset({3, 8, 9, 10, 11})


class TestValidFraction:
    def test_all_valid_in_field(self) -> None:
        field = np.ones((10, 10), dtype=bool)
        eff = np.ones((10, 10), dtype=bool)
        assert valid_fraction(field, eff) == 1.0

    def test_half_masked(self) -> None:
        field = np.ones((10, 10), dtype=bool)
        eff = field.copy()
        eff[:5, :] = False
        assert valid_fraction(field, eff) == pytest.approx(0.5)

    def test_empty_field_is_zero_not_nan(self) -> None:
        field = np.zeros((10, 10), dtype=bool)
        eff = np.zeros((10, 10), dtype=bool)
        assert valid_fraction(field, eff) == 0.0

    def test_pixels_outside_field_do_not_count(self) -> None:
        field = np.zeros((10, 10), dtype=bool)
        field[:5, :] = True  # 50 in-field pixels
        eff = field.copy()  # all in-field pixels valid
        assert valid_fraction(field, eff) == 1.0


class TestValidGate:
    def _scene(self, cloud_rows: int):
        """A 10x10 field where `cloud_rows` top rows are masked cloud."""
        red = np.full((10, 10), 600, dtype=np.float32)
        nir = np.full((10, 10), 3000, dtype=np.float32)
        scl = np.full((10, 10), 4, dtype=np.uint8)  # vegetation
        scl[:cloud_rows, :] = 9  # cloud high-probability
        field = np.ones((10, 10), dtype=bool)
        ndvi = compute_ndvi(red, nir)
        eff = effective_mask(field, scl_valid_mask(scl), ndvi)
        return valid_fraction(field, eff)

    def test_clear_scene_passes(self) -> None:
        assert self._scene(0) >= MIN_VALID_FRACTION

    def test_scene_just_below_threshold_fails(self) -> None:
        # 5 of 10 rows clouded -> 0.50 valid < 0.60
        assert self._scene(5) < MIN_VALID_FRACTION

    def test_scene_at_threshold_passes(self) -> None:
        # 4 of 10 rows clouded -> 0.60 valid == threshold
        assert self._scene(4) >= MIN_VALID_FRACTION


class TestSummarize:
    def test_percentiles_and_median(self) -> None:
        ndvi = np.linspace(0.0, 1.0, 101, dtype=np.float32).reshape(101, 1)
        eff = np.ones((101, 1), dtype=bool)
        stats = summarize(ndvi, eff)
        assert stats is not None
        assert stats["median"] == pytest.approx(0.5, abs=0.01)
        assert stats["p10"] == pytest.approx(0.1, abs=0.01)
        assert stats["p90"] == pytest.approx(0.9, abs=0.01)
        assert stats["n_pixels"] == 101

    def test_only_effective_pixels_are_counted(self) -> None:
        ndvi = np.array([[0.8, 0.8, -0.9]], dtype=np.float32)
        eff = np.array([[True, True, False]], dtype=bool)
        stats = summarize(ndvi, eff)
        assert stats is not None
        assert stats["n_pixels"] == 2
        assert stats["mean"] == pytest.approx(0.8)

    def test_no_effective_pixels_returns_none(self) -> None:
        ndvi = np.zeros((4, 4), dtype=np.float32)
        eff = np.zeros((4, 4), dtype=bool)
        assert summarize(ndvi, eff) is None


class TestZonalStats:
    def test_produces_nine_zones_indexed_row_major(self) -> None:
        ndvi = np.full((9, 9), 0.5, dtype=np.float32)
        field = np.ones((9, 9), dtype=bool)
        eff = field.copy()
        zones = zonal_stats(ndvi, field, eff)
        assert len(zones) == 9
        coords = {(z["row"], z["col"]) for z in zones}
        assert coords == {(r, c) for r in range(3) for c in range(3)}

    def test_a_declining_corner_shows_in_its_zone(self) -> None:
        ndvi = np.full((9, 9), 0.7, dtype=np.float32)
        ndvi[:3, :3] = 0.2  # north-west corner depressed
        field = np.ones((9, 9), dtype=bool)
        eff = field.copy()
        zones = {(z["row"], z["col"]): z for z in zonal_stats(ndvi, field, eff)}
        nw = zones[(0, 0)]["stats"]
        center = zones[(1, 1)]["stats"]
        assert nw is not None and center is not None
        assert nw["median"] == pytest.approx(0.2)
        assert center["median"] == pytest.approx(0.7)

    def test_a_fully_clouded_zone_reports_zero_valid_and_no_stats(self) -> None:
        ndvi = np.full((9, 9), 0.6, dtype=np.float32)
        field = np.ones((9, 9), dtype=bool)
        eff = field.copy()
        eff[:3, :3] = False  # NW zone entirely masked
        zones = {(z["row"], z["col"]): z for z in zonal_stats(ndvi, field, eff)}
        assert zones[(0, 0)]["valid_pct"] == 0.0
        assert zones[(0, 0)]["stats"] is None
        assert zones[(1, 1)]["valid_pct"] == 100.0
