"""In-memory / file-backed tournament state for preview when Mongo is unavailable."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from versusworld.config import DATA_DIR
from versusworld.countries import (
    compute_neighbors,
    load_geometry_cache,
    load_roster,
    random_empire_color,
)
from versusworld.logger import get_logger

logger = get_logger(__name__)
LOCAL_STATE = DATA_DIR / "local_state.json"


@dataclass
class LocalCountry:
    country_id: str
    name: str
    emoji: str
    color: list[int]
    owner_id: str
    alive: bool = True
    centroid_lon: float = 0.0
    centroid_lat: float = 0.0
    neighbors: list[str] = field(default_factory=list)

    def save(self) -> None:
        pass  # no-op; batch-saved via save_local_state


def build_local_countries(force: bool = False) -> list[LocalCountry]:
    if LOCAL_STATE.exists() and not force:
        return load_local_countries()

    roster = load_roster()
    cache = load_geometry_cache()
    ids = [c.id for c in roster if c.id in cache]
    neighbors = compute_neighbors(ids, cache)

    countries: list[LocalCountry] = []
    for cdef in roster:
        if cdef.id not in cache:
            continue
        lon, lat = cache[cdef.id]["centroid"]
        countries.append(
            LocalCountry(
                country_id=cdef.id,
                name=cdef.name,
                emoji=cdef.emoji,
                color=random_empire_color(),
                owner_id=cdef.id,
                alive=True,
                centroid_lon=lon,
                centroid_lat=lat,
                neighbors=neighbors.get(cdef.id, []),
            )
        )
    save_local_state(countries)
    logger.info("Built local state with %d countries", len(countries))
    return countries


def save_local_state(countries: list[LocalCountry]) -> None:
    LOCAL_STATE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_STATE.write_text(
        json.dumps([asdict(c) for c in countries], indent=2),
        encoding="utf-8",
    )


def load_local_countries() -> list[LocalCountry]:
    data = json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
    return [LocalCountry(**row) for row in data]
