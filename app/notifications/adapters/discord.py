from typing import List, Optional
from .generic import _make_apobj, _notify_with_retry
from .base import AdapterBase, AdapterResult


class DiscordAdapter(AdapterBase):
    def __init__(self, webhooks: Optional[List[str]] = None):
        self.webhooks = list(webhooks or [])

    def _normalize(self, u: str) -> str:
        try:
            low = (u or '').lower()
            if low.startswith('discord://'):
                return 'https://discord.com/api/webhooks/' + u.split('://', 1)[1].lstrip('/')
            if 'discord' in low and '/webhooks/' in low:
                if low.startswith('http'):
                    return u
                else:
                    return 'https://' + u
            return u
        except Exception:
            return u

    def send(self, title: str, body: str, body_format: object = None, attach: Optional[str] = None, context: str = '') -> AdapterResult:
        """Send using Apprise so Discord uses the same transport as other adapters."""
        normalized = [self._normalize(w) for w in self.webhooks]
        apobj, added, err = _make_apobj(normalized)
        if apobj is None:
            return AdapterResult(channel='discord', success=False, detail=err)
        if added == 0:
            return AdapterResult(channel='discord', success=False, detail='no valid discord webhook URLs added')

        ok, detail = _notify_with_retry(apobj, title=title, body=body, body_format=body_format, attach=attach)
        if ok:
            return AdapterResult(channel='discord', success=True)
        return AdapterResult(channel='discord', success=False, detail=f'notify exception: {detail}')