"""Resolve previous WorldMatch from Facebook reactions and apply conquest."""

from __future__ import annotations

import random

from versusworld.countries import conquer
from versusworld.db import WorldCountry, WorldMatch
from versusworld.fb import FaceAPI
from versusworld.logger import get_logger
from versusworld.render import render_winner

logger = get_logger(__name__)


def resolve_last_match(fb: FaceAPI | None = None) -> str:
    """
    Tally reactions on the latest unresolved match, conquer, render winner art.
    Returns caption fragment (may be empty if no prior match).
    """
    fb = fb or FaceAPI()
    matches = WorldMatch.find().sort(-WorldMatch.id).limit(1).to_list()
    if not matches:
        return ""

    match = matches[0]
    if match.resolved:
        # Already resolved — still provide caption from stored winner
        if match.winner_id:
            winner = WorldCountry.find_one(WorldCountry.country_id == match.winner_id).run()
            if winner:
                return (
                    f"Last round winner: {winner.emoji} {winner.name}, "
                    f"with {match.winner_votes or 0} votes"
                )
        return ""

    c1 = WorldCountry.find_one(WorldCountry.country_id == match.country1_id).run()
    c2 = WorldCountry.find_one(WorldCountry.country_id == match.country2_id).run()
    if not c1 or not c2:
        logger.error("Match countries missing in DB")
        return ""

    p1_votes = fb.post_reaction_count(match.post_id, match.p1_reaction)
    p2_votes = fb.post_reaction_count(match.post_id, match.p2_reaction)
    logger.info("Votes: %s=%d %s=%d", c1.name, p1_votes, c2.name, p2_votes)

    if p1_votes > p2_votes:
        winner, loser, votes = c1, c2, p1_votes
    elif p2_votes > p1_votes:
        winner, loser, votes = c2, c1, p2_votes
    else:
        winner, loser = random.choice([(c1, c2), (c2, c1)])
        votes = p1_votes
        logger.info("Tie — random winner: %s", winner.name)

    conquer(winner.country_id, loser.country_id)

    match.winner_id = winner.country_id
    match.loser_id = loser.country_id
    match.winner_votes = votes
    match.resolved = True
    match.save()

    render_winner(winner.country_id, winner.name, votes)

    return f"Last round winner: {winner.emoji} {winner.name}, with {votes} votes"
