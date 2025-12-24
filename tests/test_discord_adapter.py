import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.notifications.adapters.discord import DiscordAdapter
from app.notifications.adapters import generic


def test_discord_adapter_sends_via_apprise(monkeypatch):
    calls = {'urls': None, 'seq': []}

    def fake_make_apobj(urls=None):
        calls['urls'] = urls
        return object(), 1, None

    def fake_notify(apobj, title, body, body_format, attach=None, context=None):
        calls['seq'].append({'title': title, 'body': body, 'format': body_format, 'attach': attach})
        return True, None

    # Patch both the generic module and the local adapter-imported references
    monkeypatch.setattr(generic, '_make_apobj', fake_make_apobj)
    monkeypatch.setattr(generic, '_notify_with_retry', fake_notify)
    monkeypatch.setattr('app.notifications.adapters.discord._make_apobj', fake_make_apobj)
    monkeypatch.setattr('app.notifications.adapters.discord._notify_with_retry', fake_notify)

    da = DiscordAdapter(webhooks=['discord://id/token'])
    title = 'Job Complete'
    body = '<h1>Result</h1>All stacks succeeded.'
    res = da.send(title, body, None, attach='path/to/file.log', embed_options={'footer':'Job 1','fields':[{'name':'Test','value':'Value','inline':True}]})
    # because body contains HTML and an attachment, we expect two sends: embeds then attachment
    assert len(calls['seq']) >= 2
    first = calls['seq'][0]
    second = calls['seq'][1]
    assert first['attach'] is None
    # The HTML body is converted to plain/markdown before sending; ensure title text is present
    assert 'Result' in first['body']
    assert second['attach'] == 'path/to/file.log'
    assert len(second['body']) <= 2000
    assert res.success is True
    # URLs are normalized to https webhook form
    assert 'discord.com/api/webhooks' in calls['urls'][0]
