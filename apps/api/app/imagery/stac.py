"""Earth Search STAC queries for Sentinel-2 L2A scenes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from pystac_client import Client
from pystac_client.exceptions import APIError

logger = logging.getLogger(__name__)

STAC_URL: Final = "https://earth-search.aws.element84.com/v1"
COLLECTION: Final = "sentinel-2-l2a"
LOOKBACK_DAYS: Final = 45
MAX_CLOUD_COVER: Final = 60

# Earth Search exposes bands under these asset keys (not "B04"/"B08"/"SCL").
RED_ASSET: Final = "red"
NIR_ASSET: Final = "nir"
SCL_ASSET: Final = "scl"
_REQUIRED_ASSETS: Final = (RED_ASSET, NIR_ASSET, SCL_ASSET)


class StacError(RuntimeError):
    """The STAC catalog could not be searched."""


@dataclass(frozen=True)
class Scene:
    """A single Sentinel-2 pass over the field, with COG hrefs for the bands."""

    scene_id: str
    date: datetime
    cloud_cover: float
    red_href: str
    nir_href: str
    scl_href: str


def _to_scene(item: object) -> Scene | None:
    assets = getattr(item, "assets", {})
    if not all(key in assets for key in _REQUIRED_ASSETS):
        return None
    dt = getattr(item, "datetime", None)
    if dt is None:
        return None
    return Scene(
        scene_id=str(getattr(item, "id", "")),
        date=dt,
        cloud_cover=float(item.properties.get("eo:cloud_cover", 0.0)),  # type: ignore[attr-defined]
        red_href=assets[RED_ASSET].href,
        nir_href=assets[NIR_ASSET].href,
        scl_href=assets[SCL_ASSET].href,
    )


def search_scenes(
    bbox: tuple[float, float, float, float],
    *,
    now: datetime | None = None,
    lookback_days: int = LOOKBACK_DAYS,
    max_cloud_cover: int = MAX_CLOUD_COVER,
) -> list[Scene]:
    """Scenes intersecting `bbox` in the last `lookback_days`, cloud below cutoff.

    Returned newest-first. `now` is injectable for deterministic testing.
    """
    now = now or datetime.now(UTC)
    start = now - timedelta(days=lookback_days)

    try:
        client = Client.open(STAC_URL)
        search = client.search(
            collections=[COLLECTION],
            bbox=bbox,
            datetime=f"{start.isoformat()}/{now.isoformat()}",
            query={"eo:cloud_cover": {"lt": max_cloud_cover}},
        )
        items = list(search.items())
    except (APIError, OSError) as exc:
        logger.warning("STAC search failed: %s", exc)
        raise StacError("Could not reach the satellite catalog.") from exc

    scenes = [scene for item in items if (scene := _to_scene(item)) is not None]
    scenes.sort(key=lambda s: s.date, reverse=True)
    return scenes
