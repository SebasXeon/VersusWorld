"""World Tournament orchestration — one scheduled cycle."""

from __future__ import annotations

import random
from datetime import date

from versusworld.config import Settings, temp_dir
from versusworld.countries import pick_match
from versusworld.db import DB, WorldCountry, WorldMatch, WorldTournament
from versusworld.fb import FaceAPI
from versusworld.globe import render_globe
from versusworld.logger import get_logger
from versusworld.render import render_versus
from versusworld.winner import resolve_last_match

logger = get_logger(__name__)

REACTIONS = ["Love", "Wow", "Haha"]


def run_local(dry_run: bool = True, use_static: bool = False) -> None:
    """File-backed dry cycle for machines without Mongo."""
    from versusworld.local_state import build_local_countries

    countries = build_local_countries()
    alive = [c for c in countries if c.alive]
    if len(alive) < 2:
        logger.info("Not enough alive countries")
        return

    c1, c2 = pick_match(countries)
    reactions = REACTIONS.copy()
    random.shuffle(reactions)
    r1, r2 = reactions[0], reactions[1]

    globe_path = temp_dir() / "globe.png"
    render_globe(c1.country_id, c2.country_id, globe_path, countries=countries)
    versus_path = render_versus(
        globe_path,
        c1.name,
        c2.name,
        r1,
        r2,
        use_static=use_static,
        emoji1=c1.emoji,
        emoji2=c2.emoji,
    )
    caption = (
        f"[World Tournament]\n"
        f"{c1.emoji} {c1.name} vs {c2.emoji} {c2.name}\n"
        f"Empires remaining: {len(alive)}"
    )
    logger.info("Local dry-run caption:\n%s", caption)
    logger.info("Images: %s | %s", versus_path, globe_path)


def run(dry_run: bool = False, use_static: bool = False) -> None:
    """
    Full cycle: resolve previous match → pick next → render → post (unless dry_run).
    """
    settings = Settings()
    DB(settings.MONGO_DB_URI, settings.MONGO_DB_NAME)

    tournament = WorldTournament.find_one(WorldTournament.ended == False).run()  # noqa: E712
    if not tournament:
        raise RuntimeError("No active World Tournament. Run `versusworld init` first.")

    alive = WorldCountry.find(WorldCountry.alive == True).count()  # noqa: E712
    if alive <= 1:
        winner = WorldCountry.find_one(WorldCountry.alive == True).run()  # noqa: E712
        msg = (
            f"World Tournament finished! Winner: {winner.emoji} {winner.name}"
            if winner
            else "World Tournament finished!"
        )
        logger.info(msg)
        tournament.ended = True
        tournament.alive_count = alive
        tournament.save()
        if not dry_run and settings.PAGE_ACCESS_TOKEN:
            FaceAPI().post(f"[World Tournament]\n{msg}", str(temp_dir() / "versus.png"))
        return

    fb = FaceAPI() if not dry_run else None
    last_msg = ""
    if not dry_run:
        last_msg = resolve_last_match(fb)
    else:
        logger.info("Dry run — skipping reaction resolve / conquest")

    # Re-check after conquest
    alive = WorldCountry.find(WorldCountry.alive == True).count()  # noqa: E712
    if alive <= 1:
        winner = WorldCountry.find_one(WorldCountry.alive == True).run()  # noqa: E712
        tournament.alive_count = alive
        tournament.ended = True
        tournament.save()
        msg = f"World Tournament finished! Winner: {winner.emoji} {winner.name}" if winner else "Done"
        logger.info(msg)
        return

    c1, c2 = pick_match()
    reactions = REACTIONS.copy()
    random.shuffle(reactions)
    r1, r2 = reactions[0], reactions[1]

    globe_path = temp_dir() / "globe.png"
    render_globe(c1.country_id, c2.country_id, globe_path)

    versus_path = render_versus(
        globe_path,
        c1.name,
        c2.name,
        r1,
        r2,
        use_static=use_static,
        emoji1=c1.emoji,
        emoji2=c2.emoji,
    )

    caption = (
        f"[World Tournament]\n"
        f"{c1.emoji} {c1.name} vs {c2.emoji} {c2.name}\n"
        f"Empires remaining: {alive}"
    )
    if last_msg:
        caption += f"\n\n{last_msg}"

    if dry_run:
        logger.info("Dry run caption:\n%s", caption)
        logger.info("Images at %s and %s", versus_path, globe_path)
        return

    if not settings.PAGE_ACCESS_TOKEN:
        raise RuntimeError("PAGE_ACCESS_TOKEN not set")

    assert fb is not None
    post_id = fb.post(caption, str(versus_path))
    WorldMatch(
        post_id=post_id,
        country1_id=c1.country_id,
        country2_id=c2.country_id,
        p1_reaction=r1,
        p2_reaction=r2,
        match_date=date.today(),
        resolved=False,
    ).insert()

    if last_msg:
        winner_img = temp_dir() / "winner.png"
        if winner_img.exists():
            fb.comment_post_photo(post_id, str(winner_img), last_msg)

    tournament.alive_count = alive
    tournament.save()
    logger.info("Posted World Tournament: %s vs %s (%s)", c1.name, c2.name, post_id)
