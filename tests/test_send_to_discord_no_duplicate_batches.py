from app.notifications.discord_dispatch import send_to_discord


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def send(self, title, body, body_format=None, attach=None, context='', embed_options=None):
        self.calls.append({'title': title, 'body': body, 'body_format': body_format, 'attach': attach, 'context': context, 'embed_options': embed_options})
        return type('R', (), {'success': True, 'detail': None})


def test_batches_are_distinct():
    fa = FakeAdapter()
    title = 'T'
    body_html = '<h2>big</h2>'
    compact_text = 'X' * 5000

    # Create sections with distinct content so we can verify batches are not identical
    sections = [f"Sec{i}\n{"x"*300}" for i in range(1, 6)]

    res = send_to_discord(fa, title, body_html, compact_text, sections, attach_file=None, embed_options={'footer': 'F'}, max_desc=800, pause=0)
    assert res['sent_any'] is True
    # Ensure more than one batch created
    assert len(fa.calls) > 1
    bodies = [c['body'] for c in fa.calls if c['context'] in ('discord_section', 'discord_single')]
    # No two batches should be exactly identical
    assert len(set(bodies)) == len(bodies)
