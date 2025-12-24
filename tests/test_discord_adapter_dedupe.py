def test_discard_duplicate_webhooks(monkeypatch):
    calls = []

    def fake_make_apobj(urls=None):
        calls.append(('make', list(urls)))
        return object(), len(list(urls)), None

    def fake_notify(apobj, title, body, body_format=None, attach=None):
        calls.append(('notify', title, body, attach))
        return True, None

    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', fake_make_apobj)
    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    from app.notifications.adapters.discord import DiscordAdapter

    # Provide duplicate webhook URLs
    da = DiscordAdapter(webhooks=['discord://id/token', 'discord://id/token', 'discord://other/abc'])
    res = da.send('T', 'B', attach=None)

    # _make_apobj should be called with deduplicated URLs
    assert ('make', ['https://discord.com/api/webhooks/id/token', 'https://discord.com/api/webhooks/other/abc']) in calls
    assert res.success
