"""Country roster, Natural Earth geometries, adjacency, and matchmaking."""

from __future__ import annotations

import colorsys
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cartopy.io.shapereader as shpreader
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from versusworld.config import DATA_DIR
from versusworld.db import WorldCountry, WorldMatch, WorldTournament
from versusworld.logger import get_logger

logger = get_logger(__name__)

COUNTRIES_JSON = DATA_DIR / "countries.json"
GEOM_CACHE = DATA_DIR / "geometries.json"


@dataclass
class CountryDef:
    id: str
    name: str
    emoji: str
    ne_iso_a2: list[str] = field(default_factory=list)
    ne_adm0_a3: list[str] = field(default_factory=list)
    ne_names: list[str] = field(default_factory=list)


def load_roster() -> list[CountryDef]:
    with open(COUNTRIES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return [
        CountryDef(
            id=c["id"],
            name=c["name"],
            emoji=c["emoji"],
            ne_iso_a2=c.get("ne_iso_a2", []),
            ne_adm0_a3=c.get("ne_adm0_a3", []),
            ne_names=c.get("ne_names", []),
        )
        for c in data["countries"]
    ]


def random_empire_color() -> list[int]:
    """Mid-saturation, mid-value color — avoid harsh / too light / too dark."""
    h = random.random()
    s = random.uniform(0.45, 0.72)
    v = random.uniform(0.45, 0.72)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return [int(r * 255), int(g * 255), int(b * 255)]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def geodesic_midpoint(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> tuple[float, float]:
    """Approximate geodesic midpoint in lon/lat degrees."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    λ1, λ2 = math.radians(lon1), math.radians(lon2)
    Δλ = λ2 - λ1
    bx = math.cos(φ2) * math.cos(Δλ)
    by = math.cos(φ2) * math.sin(Δλ)
    φ3 = math.atan2(
        math.sin(φ1) + math.sin(φ2),
        math.sqrt((math.cos(φ1) + bx) ** 2 + by**2),
    )
    λ3 = λ1 + math.atan2(by, math.cos(φ1) + bx)
    return math.degrees(λ3), math.degrees(φ3)


def _record_attrs(rec) -> dict[str, str]:
    attrs = {}
    for key in ("ISO_A2", "ISO_A2_EH", "ADM0_A3", "ADM0_A3_IS", "NAME", "NAME_LONG", "ADMIN"):
        try:
            val = rec.attributes.get(key)
            if val is not None:
                attrs[key] = str(val).strip()
        except Exception:
            pass
    return attrs


def _load_ne_records(resolution: str = "50m") -> list[tuple[Any, dict[str, str]]]:
    """Load Natural Earth countries + map units (Greenland, etc.)."""
    records: list[tuple[Any, dict[str, str]]] = []
    for category_name in ("admin_0_countries", "admin_0_map_units"):
        try:
            path = shpreader.natural_earth(
                resolution=resolution, category="cultural", name=category_name
            )
            reader = shpreader.Reader(path)
            for rec in reader.records():
                geom = rec.geometry
                if geom is None or geom.is_empty:
                    continue
                records.append((geom, _record_attrs(rec)))
        except Exception as exc:
            logger.warning("Failed loading %s: %s", category_name, exc)
    return records


def _match_record(cdef: CountryDef, attrs: dict[str, str]) -> bool:
    iso = attrs.get("ISO_A2") or attrs.get("ISO_A2_EH") or ""
    adm = attrs.get("ADM0_A3") or attrs.get("ADM0_A3_IS") or ""
    names = {
        attrs.get("NAME", ""),
        attrs.get("NAME_LONG", ""),
        attrs.get("ADMIN", ""),
    }
    names = {n for n in names if n}

    if iso and iso not in ("-99", "XX") and iso in cdef.ne_iso_a2:
        return True
    if adm and adm in cdef.ne_adm0_a3:
        return True
    for n in cdef.ne_names:
        if n in names:
            return True
        for rn in names:
            if n.lower() == rn.lower():
                return True
    return False


def build_geometries(
    roster: list[CountryDef] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Match roster countries to NE polygons.
    Returns {country_id: {geometry: geojson, centroid: [lon, lat]}}.
    """
    roster = roster or load_roster()
    records = _load_ne_records("50m")
    logger.info("Loaded %d Natural Earth records", len(records))

    # Claim each NE record at most once (prefer more specific roster entries later)
    claimed: set[int] = set()
    result: dict[str, dict[str, Any]] = {}

    for cdef in roster:
        matched_geoms = []
        for idx, (geom, attrs) in enumerate(records):
            if idx in claimed:
                continue
            if _match_record(cdef, attrs):
                matched_geoms.append(geom)
                claimed.add(idx)

        if not matched_geoms:
            logger.warning("No geometry for %s (%s)", cdef.id, cdef.name)
            continue

        unioned = unary_union(matched_geoms)
        if unioned.is_empty:
            continue
        # Representative point avoids centroid outside polygons
        pt = unioned.representative_point()
        result[cdef.id] = {
            "geometry": mapping(unioned),
            "centroid": [float(pt.x), float(pt.y)],
        }

    logger.info("Matched geometries for %d / %d countries", len(result), len(roster))
    return result


def save_geometry_cache(geoms: dict[str, dict[str, Any]], path: Path = GEOM_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geoms), encoding="utf-8")
    logger.info("Saved geometry cache to %s", path)


def load_geometry_cache(path: Path = GEOM_CACHE) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Geometry cache missing at {path}. Run `versusworld init` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def get_shapely(country_id: str, cache: dict[str, dict[str, Any]] | None = None):
    cache = cache or load_geometry_cache()
    return shape(cache[country_id]["geometry"])


def compute_neighbors(
    country_ids: list[str],
    cache: dict[str, dict[str, Any]],
    buffer_deg: float = 0.05,
) -> dict[str, list[str]]:
    """Countries whose polygons nearly touch are neighbors."""
    geoms = {cid: shape(cache[cid]["geometry"]) for cid in country_ids if cid in cache}
    prepared = {cid: prep(g.buffer(buffer_deg)) for cid, g in geoms.items()}
    neighbors: dict[str, list[str]] = {cid: [] for cid in geoms}

    ids = list(geoms.keys())
    for i, a in enumerate(ids):
        ga = geoms[a]
        for b in ids[i + 1 :]:
            gb = geoms[b]
            if prepared[a].intersects(gb) or prepared[b].intersects(ga):
                # Require actual touch/overlap after tiny buffer (not just bbox)
                if ga.buffer(buffer_deg).intersects(gb):
                    neighbors[a].append(b)
                    neighbors[b].append(a)

    return neighbors


def empire_ids(owner_id: str, countries: list[WorldCountry] | None = None) -> list[str]:
    countries = countries or list(WorldCountry.find_all().to_list())
    return [c.country_id for c in countries if c.owner_id == owner_id]


def empire_geometry(
    owner_id: str,
    cache: dict[str, dict[str, Any]] | None = None,
    countries: list[WorldCountry] | None = None,
):
    cache = cache or load_geometry_cache()
    ids = empire_ids(owner_id, countries)
    geoms = [shape(cache[i]["geometry"]) for i in ids if i in cache]
    if not geoms:
        return None
    return unary_union(geoms)


def empire_centroid(
    owner_id: str,
    cache: dict[str, dict[str, Any]] | None = None,
    countries: list[WorldCountry] | None = None,
) -> tuple[float, float]:
    cache = cache or load_geometry_cache()
    countries = countries or list(WorldCountry.find_all().to_list())
    by_id = {c.country_id: c for c in countries}
    ids = empire_ids(owner_id, countries)
    if not ids:
        c = by_id.get(owner_id)
        if c:
            return c.centroid_lon, c.centroid_lat
        return 0.0, 0.0

    # Area-weighted-ish: use dissolved representative point when possible
    geom = empire_geometry(owner_id, cache, countries)
    if geom is not None and not geom.is_empty:
        pt = geom.representative_point()
        return float(pt.x), float(pt.y)

    lons = [by_id[i].centroid_lon for i in ids if i in by_id]
    lats = [by_id[i].centroid_lat for i in ids if i in by_id]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def pick_match(countries: list[WorldCountry] | None = None) -> tuple[WorldCountry, WorldCountry]:
    """Random alive country vs border neighbor, else nearest by centroid."""
    countries = countries or list(WorldCountry.find_all().to_list())
    alive = [c for c in countries if c.alive]
    if len(alive) < 2:
        raise RuntimeError("Not enough alive countries for a match")

    a = random.choice(alive)
    alive_ids = {c.country_id for c in alive}
    by_id = {c.country_id: c for c in countries}

    # Alive neighbors of A's empire: any neighbor of any owned territory whose owner is alive and != A
    owned = {c.country_id for c in countries if c.owner_id == a.country_id}
    candidate_ids: set[str] = set()
    for cid in owned:
        c = by_id.get(cid)
        if not c:
            continue
        for nid in c.neighbors:
            n = by_id.get(nid)
            if not n:
                continue
            owner = by_id.get(n.owner_id)
            if owner and owner.alive and owner.country_id != a.country_id:
                candidate_ids.add(owner.country_id)

    if candidate_ids:
        b = by_id[random.choice(sorted(candidate_ids))]
        logger.info("Match via border: %s vs %s", a.name, b.name)
        return a, b

    # Fallback: nearest alive empire by centroid distance
    ax, ay = empire_centroid(a.country_id, countries=countries)
    best: WorldCountry | None = None
    best_d = float("inf")
    for other in alive:
        if other.country_id == a.country_id:
            continue
        bx, by = empire_centroid(other.country_id, countries=countries)
        d = haversine_km(ax, ay, bx, by)
        if d < best_d:
            best_d = d
            best = other

    assert best is not None
    logger.info("Match via nearest: %s vs %s (%.0f km)", a.name, best.name, best_d)
    return a, best


def conquer(winner_id: str, loser_id: str) -> None:
    """Winner annexes loser and everything the loser owned."""
    countries = list(WorldCountry.find_all().to_list())
    by_id = {c.country_id: c for c in countries}
    winner = by_id[winner_id]
    loser = by_id[loser_id]

    for c in countries:
        if c.owner_id == loser.country_id:
            c.owner_id = winner.country_id
            c.alive = False
            c.save()

    loser.alive = False
    loser.owner_id = winner.country_id
    loser.save()

    alive_count = WorldCountry.find(WorldCountry.alive == True).count()  # noqa: E712
    tournament = WorldTournament.find_one(WorldTournament.ended == False).run()  # noqa: E712
    if tournament:
        tournament.alive_count = alive_count
        if alive_count <= 1:
            tournament.ended = True
        tournament.save()

    logger.info(
        "%s conquered %s — %d empires remain",
        winner.name,
        loser.name,
        alive_count,
    )


def init_tournament(force: bool = False) -> int:
    """Seed Mongo from roster + NE geometries. Returns country count."""
    from datetime import datetime, timezone

    from versusworld.db import DB
    from versusworld.config import Settings

    settings = Settings()
    DB(settings.MONGO_DB_URI, settings.MONGO_DB_NAME)

    existing = WorldCountry.find_all().count()
    if existing and not force:
        raise RuntimeError(
            f"Tournament already initialized ({existing} countries). Use --force to reset."
        )

    if force:
        from versusworld.db import WorldMatch

        WorldCountry.find_all().delete()
        WorldMatch.find_all().delete()
        WorldTournament.find_all().delete()

    roster = load_roster()
    if force or not GEOM_CACHE.exists():
        geoms = build_geometries(roster)
        save_geometry_cache(geoms)
    else:
        geoms = load_geometry_cache()
        logger.info("Using existing geometry cache (%d countries)", len(geoms))

    matched_ids = [c.id for c in roster if c.id in geoms]
    neighbors = compute_neighbors(matched_ids, geoms)

    count = 0
    for cdef in roster:
        if cdef.id not in geoms:
            continue
        lon, lat = geoms[cdef.id]["centroid"]
        WorldCountry(
            country_id=cdef.id,
            name=cdef.name,
            emoji=cdef.emoji,
            color=random_empire_color(),
            owner_id=cdef.id,
            alive=True,
            centroid_lon=lon,
            centroid_lat=lat,
            neighbors=neighbors.get(cdef.id, []),
            ne_names=cdef.ne_names,
            ne_iso_a2=cdef.ne_iso_a2,
            ne_adm0_a3=cdef.ne_adm0_a3,
        ).insert()
        count += 1

    WorldTournament(
        name="World Tournament",
        started_at=datetime.now(timezone.utc),
        ended=False,
        alive_count=count,
    ).insert()

    logger.info("Initialized World Tournament with %d countries", count)
    return count
