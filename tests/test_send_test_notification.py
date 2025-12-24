import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import types
from app.notifications.core import send_test_notification


def test_send_test_notification_includes_apprise_urls(monkeypatch):
    # Provide apprise URLs via get_setting
    urls = """
    discord://webhook/abc
    mailto://user@example.com
    mailtos://user:pass@smtp.example.com:587/?from=sender@example.com&to=user@example.com
    """
    monkeypatch.setattr('app.notifications.core.get_setting', lambda k, d='': urls)

    captured = {}
    def fake_notify(apobj, title, body, body_format, context=None):
        captured['title'] = title
        captured['body'] = body
        captured['format'] = body_format
        return True

    monkeypatch.setattr('app.notifications.core._apprise_notify', fake_notify)

    # Should not raise
    send_test_notification()

    # Ensure the test notification contains the human-friendly confirmation
    assert 'notification configuration is working correctly' in captured['body'].lower()
    # Ensure we do not include a 'Configured Apprise URLs' section
    assert 'configured apprise urls' not in captured['body'].lower()

    # Ensure HTML is sent for test notification
    import apprise
    assert captured['format'] == apprise.NotifyFormat.HTML
    assert '<h2>' in captured['body'] or '<p>' in captured['body']
