import os
from app.notifications.adapters.discord import DiscordAdapter


def fake_make_apobj(urls):
    class FakeAp:
        def __init__(self):
            self.last = {}

        def notify(self, **kwargs):
            # Store the last notify call so the test can inspect it
            self.last = kwargs
            return True

    return FakeAp(), 1, None


def test_truncates_content_when_attachment_and_long_body(monkeypatch):
    # Prepare a very long body
    long_body = 'A' * 5000

    # Monkeypatch _make_apobj to return our fake
    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', lambda urls: fake_make_apobj(urls))

    # Monkeypatch _notify_with_retry to call our fake's notify and capture args
    captured = {}

    def fake_notify(apobj, title, body, body_format=None, attach=None):
        captured['title'] = title
        captured['body'] = body
        captured['body_format'] = body_format
        captured['attach'] = attach
        # Simulate success
        return True, None

    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    # Create adapter with a dummy webhook and call send with an attachment
    da = DiscordAdapter(webhooks=['discord://id/token'])
    # simulate attachment path (string) to trigger attachment flow
    result = da.send(title='T', body=long_body, attach='/tmp/fake.log', context='test')

    assert result.success
    assert 'body' in captured
    assert len(captured['body']) <= 2000
    assert '(truncated' in captured['body'] or captured['body'] != long_body
