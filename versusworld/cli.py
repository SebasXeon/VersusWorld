"""CLI for VersusWorld World Tournament."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from versusworld.config import Settings, temp_dir
from versusworld.logger import get_logger

app = typer.Typer(help="VersusBot World Tournament")
logger = get_logger(__name__)


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Wipe and re-seed tournament state"),
    local: bool = typer.Option(
        False, "--local", help="File-backed state only (no Mongo) for previews"
    ),
):
    """Download Natural Earth data, seed Mongo (or local JSON), build neighbor graph."""
    from versusworld._gen_countries import main as gen_countries
    from versusworld.countries import build_geometries, load_roster, save_geometry_cache

    if not Path("data/countries.json").exists():
        gen_countries()

    # Always refresh geometry cache on init
    roster = load_roster()
    geoms = build_geometries(roster)
    save_geometry_cache(geoms)

    if local:
        from versusworld.local_state import build_local_countries

        countries = build_local_countries(force=force)
        typer.echo(f"Initialized local state with {len(countries)} countries.")
        return

    from versusworld.countries import init_tournament

    count = init_tournament(force=force)
    typer.echo(f"Initialized with {count} countries.")


@app.command()
def run(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Render locally without Facebook / without resolving votes"
    ),
    use_static: bool = typer.Option(False, "--static-bg", help="Use static generated backgrounds"),
    local: bool = typer.Option(
        False, "--local", help="Use file-backed state (no Mongo)"
    ),
):
    """One tournament cycle (every 2 hours in production)."""
    from versusworld.world import run as world_run
    from versusworld.world import run_local

    if local:
        run_local(dry_run=True, use_static=use_static)
    else:
        world_run(dry_run=dry_run, use_static=use_static)


@app.command()
def preview(
    country1: Optional[str] = typer.Option(None, "--c1", help="Country id for side 1"),
    country2: Optional[str] = typer.Option(None, "--c2", help="Country id for side 2"),
):
    """Render a local versus image without posting (file-backed state, no Mongo)."""
    from versusworld.countries import pick_match
    from versusworld.globe import render_globe
    from versusworld.local_state import build_local_countries
    from versusworld.render import render_versus

    countries = build_local_countries()
    by_id = {c.country_id: c for c in countries}

    if country1 and country2:
        c1, c2 = by_id.get(country1), by_id.get(country2)
        if not c1 or not c2:
            raise typer.BadParameter("Unknown country id(s)")
    else:
        c1, c2 = pick_match(countries)

    globe_path = temp_dir() / "globe.png"
    render_globe(c1.country_id, c2.country_id, globe_path, countries=countries)
    out = render_versus(
        globe_path,
        c1.name,
        c2.name,
        "Love",
        "Wow",
        emoji1=c1.emoji,
        emoji2=c2.emoji,
    )
    typer.echo(f"Preview written to {out}")


@app.command("schedule")
def schedule_loop(
    hours: float = typer.Option(2.0, "--hours", help="Interval between runs"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Run forever, sleeping `hours` between cycles (default 2h)."""
    from versusworld.world import run as world_run

    interval = max(hours, 0.01) * 3600
    typer.echo(f"Scheduling World Tournament every {hours}h")
    while True:
        try:
            world_run(dry_run=dry_run)
        except Exception as exc:
            logger.exception("Cycle failed: %s", exc)
        logger.info("Sleeping %.1f hours…", hours)
        time.sleep(interval)


@app.command()
def status(
    local: bool = typer.Option(False, "--local", help="Read file-backed state"),
):
    """Print tournament alive count and last match."""
    if local:
        from versusworld.local_state import build_local_countries

        countries = build_local_countries()
        alive = sum(1 for c in countries if c.alive)
        typer.echo(f"Local state — Alive: {alive} / {len(countries)}")
        return

    from versusworld.db import DB, WorldCountry, WorldMatch, WorldTournament

    settings = Settings()
    DB(settings.MONGO_DB_URI, settings.MONGO_DB_NAME)
    tournaments = WorldTournament.find().sort(-WorldTournament.id).limit(1).to_list()
    t = tournaments[0] if tournaments else None
    alive = WorldCountry.find(WorldCountry.alive == True).count()  # noqa: E712
    total = WorldCountry.find_all().count()
    typer.echo(f"Tournament: {t.name if t else 'none'} ended={t.ended if t else 'n/a'}")
    typer.echo(f"Alive: {alive} / {total}")
    matches = WorldMatch.find().sort(-WorldMatch.id).limit(1).to_list()
    if matches:
        m = matches[0]
        typer.echo(
            f"Last match: {m.country1_id} vs {m.country2_id} "
            f"resolved={m.resolved} winner={m.winner_id}"
        )


if __name__ == "__main__":
    app()
