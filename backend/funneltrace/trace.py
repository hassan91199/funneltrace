import json
import time
from collections.abc import Callable, Iterator

from funneltrace.repository import LeadRepository, TraceEvent


def event_json(event: TraceEvent) -> dict:
    return {
        "id": event.id,
        "type": event.type,
        "lead_id": event.lead_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "payload": event.payload,
    }


def format_sse(event_id: int, event_type: str, data: dict) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data)}\n\n"


def stream_events(
    repo: LeadRepository,
    lead_id: str | None = None,
    after: int = 0,
    follow: bool = True,
    poll_interval: float = 0.5,
    keepalive_every: int = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """Server-sent events: replay everything after `after`, then (if `follow`) keep
    polling for new events. Event ids are the cursor, so a client can resume with
    Last-Event-ID and neither miss nor repeat an event."""
    idle = 0
    while True:
        events = repo.events_after(after, lead_id)
        for event in events:
            after = event.id
            yield format_sse(event.id, event.type, event_json(event))
        if not follow:
            return
        if events:
            idle = 0
        else:
            idle += 1
            if idle >= keepalive_every:
                idle = 0
                yield ": keepalive\n\n"
        sleep(poll_interval)
