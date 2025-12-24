import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import types
from app.notifications.adapters.mailto import MailtoAdapter
from app.notifications.adapters import generic
from app.notifications.core import get_setting


def test_send_no_urls(monkeypatch):
    # No apprise_urls configured -> adapter should return failure
    monkeypatch.setattr('app.notifications.adapters.mailto.get_setting', lambda k, d='': '')
    adapter = MailtoAdapter()
    res = adapter.send('Test', 'Body', None)
    assert res.success is False
    assert 'no mailto' in (res.detail or '').lower()


def test_send_with_urls_success(monkeypatch):
    # Provide a dummy apprise object via _make_apobj
    dummy = types.SimpleNamespace()
    dummy.notify = lambda **kwargs: True

    def fake_make_apobj(urls=None):
        return dummy, 1, None

    # Patch the module-level _make_apobj used by MailtoAdapter
    import app.notifications.adapters.mailto as mailto_mod
    monkeypatch.setattr(mailto_mod, '_make_apobj', fake_make_apobj)

    adapter = MailtoAdapter(urls=['mailto://user@example.com'])
    res = adapter.send('Test', 'Body', None)
    assert res.success is True
