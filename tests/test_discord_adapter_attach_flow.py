def test_embeds_then_attachment(monkeypatch):
    calls = []

    def fake_make_apobj(urls=None):
        return object(), 1, None

    def fake_notify(apobj, title, body, body_format=None, attach=None):
        # record calls in order
        calls.append({'title': title, 'body': body, 'body_format': body_format, 'attach': attach})
        # emulate success for both calls
        return True, None

    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', fake_make_apobj)
    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    from app.notifications.adapters.discord import DiscordAdapter

    long_body = '<h1>Title</h1>' + ('A' * 3000)
    da = DiscordAdapter(webhooks=['discord://id/token'])
    res = da.send('T', long_body, attach='/tmp/fake.log', context='test', embed_options={'footer': 'F', 'fields': [{'name': 'n', 'value': 'v'}]})

    assert res.success
    # two calls: first should be the HTML/embed send (attach None), second the attachment send
    assert len(calls) == 2
    assert calls[0]['attach'] is None
    # We now convert HTML->plain/markdown before sending so expect title text
    assert 'Title' in calls[0]['body']
    assert calls[1]['attach'] == '/tmp/fake.log'
    assert isinstance(calls[1]['body'], str)
    assert len(calls[1]['body']) <= 2000


def test_embed_fail_but_attachment_succeeds(monkeypatch):
    calls = []

    def fake_make_apobj(urls=None):
        return object(), 1, None

    # first call fails, second succeeds
    def fake_notify(apobj, title, body, body_format=None, attach=None):
        calls.append({'title': title, 'body': body, 'body_format': body_format, 'attach': attach})
        if attach is None:
            return False, 'embed error'
        return True, None

    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', fake_make_apobj)
    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    from app.notifications.adapters.discord import DiscordAdapter

    body = '<p>Short</p>'
    da = DiscordAdapter(webhooks=['discord://id/token'])
    res = da.send('T', body, attach='/tmp/fake.log', context='test')

    assert res.success
    assert 'embed failed' in (res.detail or '')
    assert len(calls) == 2
    assert calls[0]['attach'] is None
    assert calls[1]['attach'] == '/tmp/fake.log'
