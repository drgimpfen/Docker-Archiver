import pytest
from app.notifications.adapters.base import AdapterResult


class FakeAdapter:
    instances = []

    def __init__(self, webhooks=None):
        self.calls = []
        FakeAdapter.instances.append(self)

    def send(self, title, body, body_format=None, attach=None, context='', embed_options=None):
        self.calls.append({'title': title, 'body': body, 'attach': attach, 'embed_options': embed_options})
        return AdapterResult(channel='discord', success=True)


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, *a, **k):
        pass

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self._row)


def test_send_archive_notification_calls_send_to_discord(monkeypatch):
    # Configure settings used by send_archive_notification
    settings = {
        'apprise_urls': 'discord://example/webhook',
        'notify_on_success': 'true',
        'notify_report_verbosity': 'full',
        'notify_attach_log': 'false',
        'notify_attach_log_on_failure': 'false',
        'base_url': 'http://localhost'
    }

    def fake_get_setting(k, default=''):
        return settings.get(k, default)

    monkeypatch.setattr('app.notifications.core.get_setting', fake_get_setting)

    # Fake DB returns a job row with a log and reclaimed_bytes
    fake_row = {'reclaimed_bytes': 0, 'log': 'line1\nline2'}
    monkeypatch.setattr('app.notifications.core.get_db', lambda: FakeConn(fake_row))

    # Replace DiscordAdapter with our fake
    monkeypatch.setattr('app.notifications.adapters.DiscordAdapter', FakeAdapter)

    # Call function
    from app.notifications.core import send_archive_notification

    archive_config = {'name': 'MyArchive'}
    stack_metrics = [{'stack_name': 'stack1', 'status': 'success', 'archive_size_bytes': 100, 'archive_path': '/archives/a.tar.gz'}]
    send_archive_notification(archive_config, 1234, stack_metrics, 65, 100)

    # Verify the fake adapter was instantiated and called
    assert FakeAdapter.instances, "DiscordAdapter was not created"
    inst = FakeAdapter.instances[-1]
    assert inst.calls, "No sends were performed to Discord"
    # Ensure at least one call included HTML body with archive name
    assert any('MyArchive' in c['body'] or 'MyArchive' in (c['title'] or '') for c in inst.calls)
