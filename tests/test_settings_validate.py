import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.routes.settings import validate_apprise_urls


def test_validate_allows_mailto_and_removes_duplicates():
    urls_text = """
    discord://abc
    mailto://user@example.com
    mailto://user@example.com
    telegram://bot/123
    """
    cleaned, blocked, dup = validate_apprise_urls(urls_text)
    assert blocked == 0
    assert dup == 1
    lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
    assert 'mailto://user@example.com' in lines
    assert 'discord://abc' in lines
    assert 'telegram://bot/123' in lines
    assert len(lines) == 3
