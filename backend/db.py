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


def ensure_indexes() -> None:
    """Idempotent index creation. Safe to call on every boot."""
    try:
        # Partial index: only documents whose username is actually a string
        # are indexed. Without this, legacy rows with username: null collide
        # with each other (null == null) and the unique index build fails,
        # leaving the collection with NO uniqueness guarantee at all.
        users_collection.create_index(
            [("username", ASCENDING)],
            unique=True,
            partialFilterExpression={"username": {"$type": "string"}},
        )

        messages_collection.create_index(
            [("session_id", ASCENDING), ("timestamp", ASCENDING)]
        )
        messages_collection.create_index(
            [("user_id", ASCENDING), ("timestamp", DESCENDING)]
        )

        sessions_collection.create_index([("user_id", ASCENDING)])

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
            coll.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])

        fitness_profiles_collection.create_index(
            [("user_id", ASCENDING)], unique=True
        )
        twin_actions_collection.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING), ("action_id", ASCENDING)],
            unique=True,
        )
        twin_reports_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )

        meditation_collection.create_index(
            [("user_id", ASCENDING), ("date", ASCENDING)], unique=True
        )
        community_collection.create_index([("created_at", DESCENDING)])

        # TTL index: Mongo expires the OTP for us, no cleanup job needed.
        otp_collection.create_index("expires_at", expireAfterSeconds=0)
        otp_collection.create_index([("email", ASCENDING)], unique=True)

        refresh_tokens_collection.create_index(
            "expires_at", expireAfterSeconds=0
        )
        refresh_tokens_collection.create_index([("jti", ASCENDING)], unique=True)

        safety_events_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
    except Exception as exc:  # pragma: no cover - index setup is best effort
        log.warning("Index setup skipped: %s", exc)


def ping() -> bool:
    try:
        client.admin.command("ping")
        return True
    except Exception:
        return False
