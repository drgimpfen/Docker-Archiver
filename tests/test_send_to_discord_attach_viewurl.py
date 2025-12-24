from app.notifications.discord_dispatch import send_to_discord


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def send(self, title, body, body_format=None, attach=None, context='', embed_options=None):
        self.calls.append({'title': title, 'body': body, 'body_format': body_format, 'attach': attach, 'context': context, 'embed_options': embed_options})
        return type('R', (), {'success': True, 'detail': None})


def test_send_to_discord_attach_includes_viewurl():
    fa = FakeAdapter()
    title = 'T'
    body_html = '<h1>Job</h1><p>Detail</p>'
    compact_text = 'Job completed'
    sections = ['Job completed']
    attach = '/tmp/f.log'
    view_url = 'https://example.org/history?job=123'

    res = send_to_discord(fa, title, body_html, compact_text, sections, attach_file=attach, embed_options=None, max_desc=100, view_url=view_url)
    assert res['sent_any'] is True
    # last call should be the attach send and include the view_url
    assert fa.calls[-1]['attach'] == attach
    assert 'View details: https://example.org/history?job=123' in fa.calls[-1]['body']
