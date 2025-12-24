from app.notifications.adapters.discord import DiscordAdapter


def test_send_avoids_title_duplication(monkeypatch):
    # Replace notify to capture the markdown body that's actually sent
    captured = {}
    def fake_make_apobj(urls=None):
        return object(), 1, None
    def fake_notify(apobj, title, body, body_format=None, attach=None):
        captured['body'] = body
        return True, None

    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', fake_make_apobj)
    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    da = DiscordAdapter(webhooks=['discord://id/token'])
    title = '[Netcup] ✅ Archive Complete: foo'
    # Body begins with the same title (plain-text)
    body = ' [Netcup] ✅ Archive Complete: foo\n\nDetails here.'

    res = da.send(title, body, embed_options=None)
    assert res.success
    # The sent body should not contain the title twice
    assert captured['body'].lower().count(title.lower()) == 1
