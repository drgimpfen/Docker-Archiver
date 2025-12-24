from typing import List, Optional, Tuple


def _make_apobj(urls: Optional[List[str]] = None) -> Tuple[Optional[object], int, Optional[str]]:
    try:
        import apprise
    except Exception as e:
        return None, 0, f'apprise not available: {e}'

    apobj = apprise.Apprise()
    added = 0
    for u in (urls or []):
        try:
            ok = apobj.add(u)
            if ok:
                added += 1
        except Exception:
            pass
    return apobj, added, None


def _notify_with_retry(apobj: object, title: str, body: str, body_format: object = None, attach: Optional[str] = None, capture_logs_on_success: bool = False) -> Tuple[bool, Optional[str]]:
    """Notify via Apprise. Capture DEBUG logs from the Apprise logger to provide
    detailed diagnostic information (response bodies, debug output).

    By default debug logs are only returned on failure. Set
    `capture_logs_on_success=True` to also return the captured logs when the
    notification succeeded (useful for debugging how many embeds Apprise posted).
    """
    import traceback, time, logging, io

    # Prepare a temporary debug handler that captures Apprise logs to a buffer
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)

    ap_log = getattr(__import__('apprise'), 'logger', None)
    prev_level = None
    attached = False
    if ap_log:
        try:
            prev_level = ap_log.level
            ap_log.addHandler(handler)
            ap_log.setLevel(logging.DEBUG)
            attached = True
        except Exception:
            attached = False

    try:
        res = apobj.notify(title=title, body=body, body_format=body_format, attach=attach)
        if bool(res):
            # If requested, return the captured logs even on success
            if capture_logs_on_success:
                logs = buf.getvalue().strip()
                return True, logs if logs else None
            return True, None

        # Notification returned False (one or more services failed). Return
        # the captured debug output if any to aid diagnostics.
        logs = buf.getvalue().strip()
        return False, logs if logs else None

    except Exception:
        # Log the full exception for improved diagnostics and attempt one retry
        traceback_str = traceback.format_exc()
        try:
            time.sleep(0.5)
            res = apobj.notify(title=title, body=body, body_format=body_format, attach=attach)
            if bool(res):
                return True, None
            retry_tb = traceback.format_exc()
            logs = buf.getvalue().strip()
            detail = f"first: {traceback_str.strip()} | retry: {retry_tb.strip()}"
            if logs:
                detail = f"{detail} | logs: {logs}"
            return False, detail
        except Exception:
            retry_tb = traceback.format_exc()
            logs = buf.getvalue().strip()
            detail = f"first: {traceback_str.strip()} | retry: {retry_tb.strip()}"
            if logs:
                detail = f"{detail} | logs: {logs}"
            return False, detail
    finally:
        # Restore logger state and clean up
        try:
            if ap_log and attached:
                ap_log.removeHandler(handler)
                if prev_level is not None:
                    ap_log.setLevel(prev_level)
        except Exception:
            pass
        try:
            buf.close()
        except Exception:
            pass


from .base import AdapterBase, AdapterResult


class GenericAdapter(AdapterBase):
    """Send to configured Apprise URLs only (generic transport adapter)."""

    def __init__(self, urls: Optional[List[str]] = None):
        self.urls = list(urls or [])

    def send(self, title: str, body: str, body_format: object = None, attach: Optional[str] = None, context: str = '') -> AdapterResult:
        apobj, added, err = _make_apobj(self.urls)
        if apobj is None:
            return AdapterResult(channel='generic', success=False, detail=err)
        if added == 0:
            return AdapterResult(channel='generic', success=False, detail='no apprise URLs added')

        ok, detail = _notify_with_retry(apobj, title=title, body=body, body_format=body_format, attach=attach)
        if ok:
            return AdapterResult(channel='generic', success=True)
        return AdapterResult(channel='generic', success=False, detail=f'notify exception: {detail}')