"""Cartopy NearsidePerspective globe rendering for World Versus."""

from __future__ import annotations

from pathlib import Path

import cartopy.crs as ccrs
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon, shape
from shapely.ops import linemerge, unary_union

from versusworld.countries import (
    empire_centroid,
    empire_geometry,
    empire_ids,
    geodesic_midpoint,
    load_geometry_cache,
)
from versusworld.db import WorldCountry
from versusworld.logger import get_logger

logger = get_logger(__name__)

HIGHLIGHT_RED = "#E53935"
HIGHLIGHT_BLUE = "#1E88E5"
DEFAULT_EDGE = "#333333"
DASHED_EDGE = "#555555"
LABEL_SPREAD_PX = 56  # how far to push labels apart from the midpoint axis
LABEL_ALPHA = 0.55


def _as_polygons(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out = []
        for g in geom.geoms:
            out.extend(_as_polygons(g))
        return out
    return []


def _polygon_to_path(poly: Polygon) -> MplPath:
    def ring_codes(coords):
        coords = list(coords)
        if len(coords) < 2:
            return [], []
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(coords) - 2) + [MplPath.CLOSEPOLY]
        return coords, codes

    verts, codes = ring_codes(poly.exterior.coords)
    for interior in poly.interiors:
        iv, ic = ring_codes(interior.coords)
        verts += iv
        codes += ic
    return MplPath(verts, codes)


def _boundary_lines(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    boundary = geom.boundary
    if isinstance(boundary, LineString):
        return [boundary]
    if isinstance(boundary, MultiLineString):
        return list(boundary.geoms)
    merged = linemerge(boundary)
    if isinstance(merged, LineString):
        return [merged]
    if isinstance(merged, MultiLineString):
        return list(merged.geoms)
    return []


def _add_filled_geom(ax, geom, facecolor, edgecolor=None, linewidth=0.0, zorder=2):
    for poly in _as_polygons(geom):
        path = _polygon_to_path(poly)
        patch = PathPatch(
            path,
            facecolor=facecolor,
            edgecolor=edgecolor or "none",
            linewidth=linewidth,
            transform=ccrs.PlateCarree(),
            zorder=zorder,
        )
        ax.add_patch(patch)


def _add_line_geom(ax, geom, color, linewidth, linestyle="solid", zorder=4):
    segments = []
    for line in _boundary_lines(geom):
        coords = list(line.coords)
        if len(coords) < 2:
            continue
        if linestyle == "dashed":
            dash_len, gap_len = 4, 3
            i = 0
            while i < len(coords) - 1:
                end = min(i + dash_len, len(coords) - 1)
                segments.append(coords[i : end + 1])
                i = end + gap_len
        else:
            segments.append(coords)
    if not segments:
        return
    lc = LineCollection(
        segments,
        colors=color,
        linewidths=linewidth,
        linestyles="solid",
        transform=ccrs.PlateCarree(),
        zorder=zorder,
    )
    ax.add_collection(lc)


def _lonlat_to_display(ax, lon: float, lat: float) -> np.ndarray | None:
    """Project lon/lat to display (pixel) coordinates; None if not visible."""
    try:
        pts = ax.projection.transform_points(
            ccrs.PlateCarree(), np.array([lon]), np.array([lat])
        )
        x, y, z = pts[0]
        # Behind the globe in NearsidePerspective
        if not np.isfinite(x) or not np.isfinite(y):
            return None
        if z is not None and np.isfinite(z) and z < 0:
            return None
        disp = ax.transData.transform((x, y))
        return np.asarray(disp, dtype=float)
    except Exception:
        return None


def _spread_label_display_positions(
    ax,
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    spread_px: float = LABEL_SPREAD_PX,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Start at each country center (display space), then push labels apart
    along the direction from the midpoint through each country center.
    """
    d1 = _lonlat_to_display(ax, lon1, lat1)
    d2 = _lonlat_to_display(ax, lon2, lat2)

    # Fallback to axes center if a point is on the far side
    bbox = ax.get_window_extent()
    center = np.array([(bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2])
    if d1 is None:
        d1 = center + np.array([-40.0, 0.0])
    if d2 is None:
        d2 = center + np.array([40.0, 0.0])

    mid = (d1 + d2) / 2.0

    def push(p: np.ndarray) -> np.ndarray:
        direction = p - mid
        norm = float(np.linalg.norm(direction))
        if norm < 1e-6:
            # Identical / overlapping centers — split horizontally
            direction = np.array([1.0 if p is d1 or (p == d1).all() else -1.0, 0.0])
            # Distinguish by which point
            direction = np.array([1.0, 0.0]) if np.allclose(p, d1) else np.array([-1.0, 0.0])
            norm = 1.0
        return p + (direction / norm) * spread_px

    return push(d1), push(d2)


def _draw_country_label(
    ax,
    display_xy: np.ndarray,
    name: str,
    color_rgb: list[int],
) -> None:
    """Sheer country-colored pill with black text at a display-space position."""
    # Convert display pixels → data coords for placement
    data_xy = ax.transData.inverted().transform(display_xy)
    face = (
        color_rgb[0] / 255,
        color_rgb[1] / 255,
        color_rgb[2] / 255,
        LABEL_ALPHA,
    )
    ax.text(
        data_xy[0],
        data_xy[1],
        name,
        fontsize=11,
        fontweight="bold",
        color="black",
        ha="center",
        va="center",
        zorder=10,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": face,
            "edgecolor": (0, 0, 0, 0.35),
            "linewidth": 0.8,
        },
        clip_on=False,
    )


def render_globe(
    country1_id: str,
    country2_id: str | None = None,
    out_path: str | Path = "globe.png",
    size_px: tuple[int, int] = (640, 640),
    dpi: int = 100,
    countries: list | None = None,
    mode: str = "match",
) -> Path:
    """
    Render a NearsidePerspective globe.
    mode="match": center between two empires, red/blue highlights + both labels.
    mode="winner": center on the winner empire, gold highlight + winner label.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if countries is None:
        countries = list(WorldCountry.find_all().to_list())
    by_id = {c.country_id: c for c in countries}
    cache = load_geometry_cache()

    c1 = by_id[country1_id]
    winner_mode = mode == "winner" or country2_id is None

    if winner_mode:
        clon, clat = empire_centroid(country1_id, cache, countries)
        lon1, lat1 = clon, clat
        lon2 = lat2 = None
        c2 = None
    else:
        assert country2_id is not None
        c2 = by_id[country2_id]
        lon1, lat1 = empire_centroid(country1_id, cache, countries)
        lon2, lat2 = empire_centroid(country2_id, cache, countries)
        clon, clat = geodesic_midpoint(lon1, lat1, lon2, lat2)

    clat = max(min(clat, 80.0), -80.0)

    width_in = size_px[0] / dpi
    height_in = size_px[1] / dpi
    fig = plt.figure(figsize=(width_in, height_in), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_subplot(
        1,
        1,
        1,
        projection=ccrs.NearsidePerspective(
            central_longitude=clon,
            central_latitude=clat,
            satellite_height=6_500_000,
        ),
    )
    ax.set_global()
    ax.set_facecolor((0, 0, 0, 0))
    ax.patch.set_alpha(0.0)

    owners: dict[str, list[str]] = {}
    for c in countries:
        owners.setdefault(c.owner_id, []).append(c.country_id)

    for owner_id, member_ids in owners.items():
        owner = by_id.get(owner_id)
        if not owner:
            continue
        color = tuple(ch / 255 for ch in owner.color)
        pieces = [shape(cache[mid]["geometry"]) for mid in member_ids if mid in cache]
        if not pieces:
            continue
        geom = unary_union(pieces)
        _add_filled_geom(ax, geom, facecolor=color, zorder=2)

    for c in countries:
        if c.country_id not in cache:
            continue
        geom = shape(cache[c.country_id]["geometry"])
        empire_members = empire_ids(c.owner_id, countries)
        if len(empire_members) > 1:
            _add_line_geom(
                ax, geom, DASHED_EDGE, linewidth=0.6, linestyle="dashed", zorder=3
            )

    HIGHLIGHT_GOLD = "#FFD54F"
    for owner_id in owners:
        geom = empire_geometry(owner_id, cache, countries)
        if geom is None:
            continue
        if winner_mode and owner_id == country1_id:
            _add_line_geom(ax, geom, HIGHLIGHT_GOLD, linewidth=2.6, zorder=6)
        elif not winner_mode and owner_id == country1_id:
            _add_line_geom(ax, geom, HIGHLIGHT_RED, linewidth=2.2, zorder=6)
        elif not winner_mode and owner_id == country2_id:
            _add_line_geom(ax, geom, HIGHLIGHT_BLUE, linewidth=2.2, zorder=6)
        else:
            _add_line_geom(ax, geom, DEFAULT_EDGE, linewidth=0.9, zorder=4)

    fig.canvas.draw()
    if winner_mode:
        disp = _lonlat_to_display(ax, lon1, lat1)
        if disp is None:
            bbox = ax.get_window_extent()
            disp = np.array([(bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2])
        # Nudge label slightly outward from dead center for readability
        center = np.array(
            [
                (ax.get_window_extent().x0 + ax.get_window_extent().x1) / 2,
                (ax.get_window_extent().y0 + ax.get_window_extent().y1) / 2,
            ]
        )
        direction = disp - center
        norm = float(np.linalg.norm(direction))
        if norm > 1e-6:
            disp = disp + (direction / norm) * 28
        _draw_country_label(ax, disp, c1.name, c1.color)
    else:
        pos1, pos2 = _spread_label_display_positions(ax, lon1, lat1, lon2, lat2)
        _draw_country_label(ax, pos1, c1.name, c1.color)
        _draw_country_label(ax, pos2, c2.name, c2.color)

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(
        out_path,
        dpi=dpi,
        bbox_inches=None,
        pad_inches=0,
        facecolor=(0, 0, 0, 0),
        edgecolor="none",
        transparent=True,
    )
    plt.close(fig)
    logger.info("Globe saved to %s (center %.1f, %.1f)", out_path, clon, clat)
    return out_path
