"""Simple in-memory SSE/pubsub utilities for job events.

This module provides thread-safe registration of listeners (queues) per job id,
and helper to send JSON-serializable events to all listeners of a job.

Note: This is an in-memory mechanism intended for single-node deployments or
for streams handled by the same worker running the job. It's not intended as a
cross-worker message bus. For multi-worker setups you should implement a
central pub/sub (Redis, etc.) if needed.
"""
from collections import defaultdict
import json
import threading
import queue
import os

_listeners = defaultdict(list)  # job_id -> list of Queue
_lock = threading.Lock()

# Optional Redis support (for multi-worker deployments)
_redis_client = None
_redis_subscribers = {}  # job_id -> {'thread': Thread, 'stop': Event}
_redis_global = None  # {'thread': Thread, 'stop': Event}
_use_redis = False

REDIS_URL = os.environ.get('REDIS_URL')
JOB_EVENTS_DEBUG = os.environ.get('JOB_EVENTS_DEBUG')

if REDIS_URL:
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # test connection
        try:
            _redis_client.ping()
            _use_redis = True
        except Exception:
            _redis_client = None
            _use_redis = False
    except Exception:
        # If redis package not available or connection fails, fall back to in-memory
        _redis_client = None
        _use_redis = False

if JOB_EVENTS_DEBUG:
    print(f"[SSE] REDIS_URL={'set' if REDIS_URL else 'not-set'}, _use_redis={_use_redis}")

# If Redis not available initially, start a background connector that will
# attempt to reconnect periodically. This allows late-start Redis or network
# readiness to still enable cross-worker event propagation.
if not _use_redis and REDIS_URL:
    def _redis_connector_loop():
        try:
            import time
            import redis
            while True:
                try:
                    client = redis.from_url(REDIS_URL, decode_responses=True)
                    client.ping()
                    # success
                    global _redis_client, _use_redis
                    _redis_client = client
                    _use_redis = True
                    if JOB_EVENTS_DEBUG:
                        print(f"[SSE] Redis connected on retry")
                    return
                except Exception:
                    if JOB_EVENTS_DEBUG:
                        print(f"[SSE] Redis not available yet, retrying in 5s")
                    time.sleep(5)
        except Exception:
            pass
    import threading
    t = threading.Thread(target=_redis_connector_loop, daemon=True)
    t.start()


def _start_redis_subscriber(job_id):
    """Start a background thread that subscribes to Redis channel for job_id and
    forwards messages into local in-memory listener queues.
    """
    if not _use_redis or job_id in _redis_subscribers:
        return

    stop_event = threading.Event()

    def run():
        try:
            pubsub = _redis_client.pubsub(ignore_subscribe_messages=True)
            channel = f"job-events:{job_id}"
            pubsub.subscribe(channel)
            while not stop_event.is_set():
                msg = pubsub.get_message(timeout=1)
                if msg and msg.get('data'):
                    data = msg['data']
                    # Forward to local queues
                    with _lock:
                        queues = list(_listeners.get(job_id, []))
                    for q in queues:
                        try:
                            q.put_nowait(data)
                        except Exception:
                            pass
        except Exception:
            # If anything goes wrong, just stop subscriber
            pass

    t = threading.Thread(target=run, daemon=True)
    _redis_subscribers[job_id] = {'thread': t, 'stop': stop_event}
    t.start()


def _start_redis_global_subscriber():
    """Start a background thread that subscribes to the global jobs-events channel.
    Forwards messages into the local global listener queues.
    """
    global _redis_global
    if not _use_redis or _redis_global is not None:
        return

    stop_event = threading.Event()

    def run():
        try:
            pubsub = _redis_client.pubsub(ignore_subscribe_messages=True)
            channel = "jobs-events"
            pubsub.subscribe(channel)
            while not stop_event.is_set():
                msg = pubsub.get_message(timeout=1)
                if msg and msg.get('data'):
                    data = msg['data']
                    # Debug log receipt
                    try:
                        if os.environ.get('JOB_EVENTS_DEBUG'):
                            print(f"[SSE] Global event RECEIVED from Redis: {data}")
                    except Exception:
                        pass
                    # Forward to global queues
                    with _lock:
                        queues = list(_global_listeners)
                    for q in queues:
                        try:
                            q.put_nowait(data)
                        except Exception:
                            pass
        except Exception as e:
            if os.environ.get('JOB_EVENTS_DEBUG'):
                print(f"[SSE] Global subscriber failed: {e}")
            # If anything goes wrong, just stop subscriber
            pass

    t = threading.Thread(target=run, daemon=True)
    _redis_global = {'thread': t, 'stop': stop_event}
    t.start()


def _stop_redis_subscriber(job_id):
    s = _redis_subscribers.get(job_id)
    if not s:
        return
    try:
        s['stop'].set()
    except Exception:
        pass
    try:
        s['thread'].join(timeout=2)
    except Exception:
        pass
    with _lock:
        try:
            del _redis_subscribers[job_id]
        except Exception:
            pass


def register_event_listener(job_id):
    q = queue.Queue()
    with _lock:
        _listeners[job_id].append(q)

    # If using Redis, ensure a subscriber thread is running for this job_id
    if _use_redis:
        _start_redis_subscriber(job_id)
    return q


def unregister_event_listener(job_id, q):
    with _lock:
        lst = _listeners.get(job_id)
        if not lst:
            return
        try:
            lst.remove(q)
        except ValueError:
            return
        if not lst:
            del _listeners[job_id]
            # Stop redis subscriber if present
            if _use_redis:
                _stop_redis_subscriber(job_id)


# Global listeners for job metadata changes
_global_listeners = []

def register_global_listener():
    q = queue.Queue()
    with _lock:
        _global_listeners.append(q)

    if _use_redis:
        _start_redis_global_subscriber()
    return q


def unregister_global_listener(q):
    with _lock:
        try:
            _global_listeners.remove(q)
        except ValueError:
            return


def send_event(job_id, event_type, payload):
    """Send a JSON event to all registered listeners for job_id.

    payload should be JSON-serializable. The function will attempt to put the
    serialized message into each listener queue (non-blocking). If Redis is
    configured, the event will also be published to the channel `job-events:<id>`
    so other workers can receive it.
    """
    data = json.dumps({'type': event_type, 'data': payload}, default=str)

    # Local in-memory delivery
    with _lock:
        queues = list(_listeners.get(job_id, []))
    for q in queues:
        try:
            q.put_nowait(data)
        except Exception:
            # best-effort; drop if queue is full or closed
            pass

    # Publish to Redis if enabled (best-effort)
    if _use_redis and _redis_client:
        try:
            channel = f"job-events:{job_id}"
            _redis_client.publish(channel, data)
        except Exception:
            pass


def send_global_event(event_type, payload):
    """Send a JSON event to all global listeners and publish to the global Redis channel.

    Event is of the form: {type: <event_type>, data: <payload>}
    """
    data = json.dumps({'type': event_type, 'data': payload}, default=str)

    # Local in-memory delivery
    with _lock:
        queues = list(_global_listeners)
    for q in queues:
        try:
            q.put_nowait(data)
        except Exception:
            pass

    # Publish to Redis global channel if enabled
    if _use_redis and _redis_client:
        try:
            _redis_client.publish('jobs-events', data)
            try:
                if JOB_EVENTS_DEBUG:
                    print(f"[SSE] Global event PUBLISHED to Redis: {data}")
            except Exception:
                pass
        except Exception as e:
            if JOB_EVENTS_DEBUG:
                print(f"[SSE] Failed to publish global event to Redis: {e}")
            pass
    else:
        if JOB_EVENTS_DEBUG:
            print("[SSE] Redis not available - global event was delivered locally but not published to Redis")