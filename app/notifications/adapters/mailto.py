from typing import List, Optional
import logging
from .generic import _make_apobj, _notify_with_retry
from .base import AdapterBase, AdapterResult
from app.utils import get_logger
from app.notifications.core import get_setting

# Reduce Apprise noise
logging.getLogger('apprise').setLevel(logging.WARNING)
logger = get_logger(__name__)


class MailtoAdapter(AdapterBase):
    """Send email notifications using mailto/mailtos URLs defined in Apprise settings.

    This adapter looks for mailto/mailtos/smtp-like URLs in the `apprise_urls` setting
    and uses Apprise to send via those transport URLs.
    """

    def __init__(self, urls: Optional[List[str]] = None):
        # Optional explicit URLs (takes precedence over settings)
        self.urls = list(urls or [])

    def _gather_urls_from_settings(self) -> List[str]:
        raw = get_setting('apprise_urls', '')
        urls = []
        for u in raw.split('\n'):
            u = u.strip()
            if not u:
                continue
            try:
                scheme = u.split(':', 1)[0].lower()
            except Exception:
                scheme = ''
            if scheme.startswith('mailto') or scheme.startswith('mailtos') or 'mail' in scheme or 'smtp' in scheme:
                urls.append(u)
        return urls

    def send(self, title: str, body: str, body_format: object = None, attach: Optional[str] = None, context: str = '') -> AdapterResult:
        urls = list(self.urls or [])
        if not urls:
            urls = self._gather_urls_from_settings()

        if not urls:
            logger.warning("Mailto adapter: no mailto/mailtos URLs configured in Apprise settings")
            return AdapterResult(channel='mailto', success=False, detail='no mailto/mailtos URLs configured')

        apobj, added, err = _make_apobj(urls)
        if apobj is None:
            logger.error("Mailto adapter: apprise not available: %s", err)
            return AdapterResult(channel='mailto', success=False, detail=err)
        if added == 0:
            logger.warning("Mailto adapter: no valid mailto URLs added")
            return AdapterResult(channel='mailto', success=False, detail='no valid mailto URLs added')

        ok, detail = _notify_with_retry(apobj, title=title, body=body, body_format=body_format, attach=attach)
        if ok:
            logger.info("Mailto adapter: notification sent via mailto/mailtos (context=%s)", context)
            return AdapterResult(channel='mailto', success=True)
        logger.error("Mailto adapter: notify failed (%s)", detail)
        return AdapterResult(channel='mailto', success=False, detail=f'notify exception: {detail}')
