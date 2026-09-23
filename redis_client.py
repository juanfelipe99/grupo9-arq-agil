import os

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0"
)

try:
    import redis
    redis_client = redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2
    )
except Exception:
    redis_client = None


def redis_disponible():
    """True solo si la libreria esta instalada y el servidor responde."""
    if redis_client is None:
        return False
    try:
        return bool(redis_client.ping())
    except Exception:
        return False
