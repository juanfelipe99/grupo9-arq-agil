import json

from redis_client import redis_client

BEHAVIOR_QUEUE = "registro_comportamiento"


def publish_behavior_event(event):
    redis_client.rpush(
        BEHAVIOR_QUEUE,
        json.dumps(event)
    )


def consume_behavior_event():
    message = redis_client.blpop(
        BEHAVIOR_QUEUE,
        timeout=1
    )

    if message is None:
        return None

    _, data = message

    return json.loads(data)