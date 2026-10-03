"""MongoDB connection and index setup.

No credentials live here. The URI comes from MONGO_URI in the environment.
"""

import logging

from pymongo import ASCENDING, DESCENDING, MongoClient

from config import settings

log = logging.getLogger(__name__)


def _configure_dns() -> None:
    """Point dnspython at a public resolver for SRV lookups.

    A mongodb+srv:// URI needs an SRV record. Plenty of home routers and
    corporate resolvers simply don't return them, and the failure surfaces
    as a confusing "DNS query name does not exist" at import time.
    """
    if not settings.DNS_NAMESERVERS:
        return
    try:
        import dns.resolver

        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = settings.DNS_NAMESERVERS
        resolver.lifetime = 10
        dns.resolver.default_resolver = resolver
        log.info("DNS resolver set to %s", ", ".join(settings.DNS_NAMESERVERS))
    except Exception as exc:
        log.warning("Could not override DNS resolver: %s", exc)


_configure_dns()

# connect=False defers the handshake to the first real query, so a database
# that is slow or unreachable can't stop the process from starting. /health
# reports the actual state.
client = MongoClient(
    settings.MONGO_URI,
    serverSelectionTimeoutMS=8000,
    connectTimeoutMS=8000,
    tz_aware=True,
    connect=False,
)
db = client[settings.MONGO_DB]

users_collection = db["users"]
sessions_collection = db["sessions"]
messages_collection = db["messages"]
journals_collection = db["journals"]
moods_collection = db["moods"]
tasks_collection = db["tasks"]
meditation_collection = db["meditation_sessions"]
sleep_collection = db["sleep_records"]
community_collection = db["community_posts"]
goals_collection = db["goals"]

# Physical fitness module.
fitness_profiles_collection = db["fitness_profiles"]   # one per user
fitness_metrics_collection = db["fitness_metrics"]     # weight/BMI history
fitness_plans_collection = db["fitness_plans"]         # generated plans
fitness_workouts_collection = db["fitness_workouts"]   # completed sessions

# Personal Health Twin.
twin_actions_collection = db["twin_actions"]   # ticked daily-plan actions
twin_reports_collection = db["twin_reports"]   # cached weekly reports

# OTPs used to live in a process-local dict, so every restart logged people
# out of the signup flow and a second worker never saw the first one's codes.
otp_collection = db["otps"]

# Every crisis escalation is written here and never updated or deleted.
safety_events_collection = db["safety_events"]

refresh_tokens_collection = db["refresh_tokens"]


def _index(collection, keys, **options) -> None:
    """Create one index, on its own. A failure is logged and skipped so it
    cannot take the indexes after it down with it — the previous version
    wrapped the whole list in a single try, which meant one bad legacy row
    in `users` silently left the OTP and refresh-token TTL indexes unbuilt."""
    try:
        collection.create_index(keys, **options)
    except Exception as exc:  # pragma: no cover - best effort by design
        log.warning("Index %s on %s skipped: %s", keys, collection.name, exc)


def ensure_indexes() -> None:
    """Idempotent index creation. Safe to call on every boot."""
    # One reachability check up front. Without it, an unreachable database
    # costs a full server-selection timeout per index and holds startup for
    # minutes; with it, the API comes up straight away and /health says why.
    if not ping():
        log.warning("Database unreachable at startup; index setup skipped")
        return

    # Partial index: only documents whose username is actually a string are
    # indexed. Without this, legacy rows with username: null collide with
    # each other (null == null) and the unique index build fails, leaving
    # the collection with NO uniqueness guarantee at all.
    _index(
        users_collection,
        [("username", ASCENDING)],
        unique=True,
        partialFilterExpression={"username": {"$type": "string"}},
    )

    _index(messages_collection, [("session_id", ASCENDING), ("timestamp", ASCENDING)])
    _index(messages_collection, [("user_id", ASCENDING), ("timestamp", DESCENDING)])
    _index(sessions_collection, [("user_id", ASCENDING)])

    for coll in (
        journals_collection,
        moods_collection,
        tasks_collection,
        sleep_collection,
        goals_collection,
        fitness_metrics_collection,
        fitness_plans_collection,
        fitness_workouts_collection,
    ):
        _index(coll, [("user_id", ASCENDING), ("created_at", DESCENDING)])

    _index(fitness_profiles_collection, [("user_id", ASCENDING)], unique=True)
    _index(
        twin_actions_collection,
        [("user_id", ASCENDING), ("date", ASCENDING), ("action_id", ASCENDING)],
        unique=True,
    )
    _index(twin_reports_collection, [("user_id", ASCENDING), ("created_at", DESCENDING)])

    _index(
        meditation_collection,
        [("user_id", ASCENDING), ("date", ASCENDING)],
        unique=True,
    )
    _index(community_collection, [("created_at", DESCENDING)])

    # TTL indexes: Mongo expires these documents for us, no cleanup job.
    _index(otp_collection, "expires_at", expireAfterSeconds=0)
    _index(otp_collection, [("email", ASCENDING)], unique=True)
    _index(refresh_tokens_collection, "expires_at", expireAfterSeconds=0)
    _index(refresh_tokens_collection, [("jti", ASCENDING)], unique=True)
    _index(refresh_tokens_collection, [("user_id", ASCENDING)])

    _index(safety_events_collection, [("user_id", ASCENDING), ("created_at", DESCENDING)])


def ping() -> bool:
    try:
        client.admin.command("ping")
        return True
    except Exception:
        return False
