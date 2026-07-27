from datetime import date, datetime
from typing import Optional

from bunnet import Document, init_bunnet
from pymongo import MongoClient
from pymongo.errors import ConfigurationError


class WorldCountry(Document):
    country_id: str
    name: str
    emoji: str
    color: list[int]
    owner_id: str
    alive: bool = True
    centroid_lon: float
    centroid_lat: float
    neighbors: list[str] = []
    ne_names: list[str] = []
    ne_iso_a2: list[str] = []
    ne_adm0_a3: list[str] = []

    class Settings:
        name = "WorldCountry"


class WorldMatch(Document):
    post_id: str
    country1_id: str
    country2_id: str
    p1_reaction: str
    p2_reaction: str
    winner_id: Optional[str] = None
    winner_votes: Optional[int] = None
    loser_id: Optional[str] = None
    match_date: Optional[date] = None
    resolved: bool = False

    class Settings:
        name = "WorldMatch"


class WorldTournament(Document):
    name: str = "World Tournament"
    started_at: datetime
    ended: bool = False
    alive_count: int = 0
    current_match_id: Optional[str] = None

    class Settings:
        name = "WorldTournament"


def _ensure_dns_nameservers() -> None:
    """
    Windows / some environments leave dnspython with an empty nameserver list,
    which breaks mongodb+srv:// SRV lookups (NoNameservers).
    """
    try:
        import dns.resolver

        resolver = dns.resolver.get_default_resolver()
        if not resolver.nameservers:
            resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
    except Exception:
        pass


class DB:
    def __init__(self, db_uri: str, db_name: str) -> None:
        _ensure_dns_nameservers()
        try:
            client = MongoClient(
                db_uri,
                serverSelectionTimeoutMS=20_000,
                connectTimeoutMS=20_000,
            )
            # Force early failure with a clear path if Atlas is unreachable
            client.admin.command("ping")
        except ConfigurationError as exc:
            raise ConfigurationError(
                f"{exc}\n"
                "Hint: mongodb+srv DNS failed. Check internet/DNS, or set "
                "MONGO_DB_URI to a standard mongodb:// host list from Atlas, "
                "or use `versusworld init --local` without Mongo."
            ) from exc
        except Exception as exc:
            raise ConnectionError(
                f"Could not connect to MongoDB ({db_name}): {exc}\n"
                "Check MONGO_DB_URI / network / Atlas IP allowlist, "
                "or use `versusworld init --local`."
            ) from exc

        init_bunnet(
            database=getattr(client, db_name),
            document_models=[WorldCountry, WorldMatch, WorldTournament],
        )
