from typing import List, Optional
from .generic import _make_apobj, _notify_with_retry
from .base import AdapterBase, AdapterResult


class SMTPAdapter(AdapterBase):
    """Construct mailto URLs from SMTP environment and user addresses and send via Apprise."""

    def __init__(self, smtp_server: Optional[str] = None, smtp_user: Optional[str] = None, smtp_password: Optional[str] = None, smtp_port: str = '587', smtp_from: Optional[str] = None, recipients: Optional[List[str]] = None):
        self.smtp_server = smtp_server
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_port = smtp_port
        self.smtp_from = smtp_from
        self.recipients = list(recipients or [])

    def _gather_recipients(self) -> List[str]:
        if self.recipients:
            return self.recipients
        try:
            from app.notifications import get_user_emails
            return get_user_emails()
        except Exception:
            return []

    def send(self, title: str, body: str, body_format: object = None, attach: Optional[str] = None, context: str = '') -> AdapterResult:
        import os
        smtp_server = self.smtp_server or os.environ.get('SMTP_SERVER')
        smtp_user = self.smtp_user or os.environ.get('SMTP_USER')
        smtp_password = self.smtp_password or os.environ.get('SMTP_PASSWORD')
        smtp_port = self.smtp_port or os.environ.get('SMTP_PORT', '587')
        smtp_from = self.smtp_from or os.environ.get('SMTP_FROM')

        if not (smtp_server and smtp_user and smtp_password and smtp_from):
            return AdapterResult(channel='email', success=False, detail='smtp configuration incomplete')

        recipients = self._gather_recipients()
        if not recipients:
            return AdapterResult(channel='email', success=False, detail='no recipients found')

        mailtos = []
        for email in recipients:
            try:
                mailto = f"mailtos://{smtp_user}:{smtp_password}@{smtp_server}:{smtp_port}/?from={smtp_from}&to={email}"
                mailtos.append(mailto)
            except Exception:
                continue

        apobj, added, err = _make_apobj(mailtos)
        if apobj is None:
            return AdapterResult(channel='email', success=False, detail=err)
        if added == 0:
            return AdapterResult(channel='email', success=False, detail='no valid mailto URLs added')

        ok, detail = _notify_with_retry(apobj, title=title, body=body, body_format=body_format, attach=attach)
        if ok:
            return AdapterResult(channel='email', success=True)
        return AdapterResult(channel='email', success=False, detail=f'notify exception: {detail}')