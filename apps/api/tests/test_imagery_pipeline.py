"""Scene dedup and the discard gate, exercised through the orchestration path."""

from datetime import UTC, datetime

import numpy as np
import pytest

from app.imagery import pipeline
from app.imagery.raster import FieldArrays
from app.imagery.stac import Scene


def scene(scene_id: str, day: int, cloud: float) -> Scene:
    return Scene(
        scene_id=scene_id,
        date=datetime(2026, 6, day, tzinfo=UTC),
        cloud_cover=cloud,
        red_href="r",
        nir_href="n",
        scl_href="s",
    )


class TestCandidatesByDate:
    def test_groups_a_duplicated_date_clearest_first(self) -> None:
        scenes = [scene("a", 25, 40.0), scene("b", 25, 3.0)]
        result = pipeline._candidates_by_date(scenes)
        assert len(result) == 1
        _day, candidates = result[0]
        # Both scenes are kept (edge-field fallback), clearest first.
        assert [s.scene_id for s in candidates] == ["b", "a"]

    def test_orders_newest_date_first(self) -> None:
        scenes = [scene("old", 10, 5.0), scene("new", 28, 5.0)]
        result = pipeline._candidates_by_date(scenes)
        assert [day.day for day, _ in result] == [28, 10]

    def test_caps_at_max_dates(self) -> None:
        scenes = [scene(str(d), d, 5.0) for d in range(1, 28)]
        result = pipeline._candidates_by_date(scenes)
        assert len(result) == pipeline.MAX_DATES


def _field_arrays(cloud_rows: int) -> FieldArrays:
    red = np.full((10, 10), 600, dtype=np.float32)
    nir = np.full((10, 10), 3000, dtype=np.float32)
    scl = np.full((10, 10), 4, dtype=np.uint8)
    scl[:cloud_rows, :] = 9  # cloud high-probability
    field_mask = np.ones((10, 10), dtype=bool)
    return FieldArrays(
        red=red, nir=nir, scl=scl, field_mask=field_mask,
        bounds_wgs84=(79.2, 10.85, 79.205, 10.855),
    )


class TestAnalyzeSceneGate:
    def test_clear_scene_yields_an_observation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pipeline, "read_field_arrays", lambda *_: _field_arrays(0))
        result = pipeline.analyze_scene(scene("clear", 25, 2.0), polygon=None)  # type: ignore[arg-type]
        assert result is not None
        assert result.valid_pct == 100.0
        assert 0.6 < result.stats["median"] <= 1.0
        assert len(result.zonal) == 9
        assert result.overlay_png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_mostly_clouded_scene_is_discarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 7 of 10 rows clouded -> 0.30 valid < 0.60 gate.
        monkeypatch.setattr(pipeline, "read_field_arrays", lambda *_: _field_arrays(7))
        result = pipeline.analyze_scene(scene("cloudy", 25, 55.0), polygon=None)  # type: ignore[arg-type]
        assert result is None
