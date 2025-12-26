import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.stacks import detect_bind_mismatches, get_mismatched_destinations


def test_ignore_tmp_downloads_mismatch(monkeypatch):
    # Simulate get_bind_mounts returning a mismatch for /tmp/downloads
    monkeypatch.setattr('app.stacks.get_bind_mounts', lambda: [
        {'source': '/host/some/other', 'destination': '/tmp/downloads'},
        {'source': '/opt/stacks', 'destination': '/opt/stacks'}
    ])

    warns = detect_bind_mismatches()
    mism = get_mismatched_destinations()

    # The /tmp/downloads mismatch should be ignored
    assert all('/tmp/downloads' not in w for w in warns)
    assert '/tmp/downloads' not in mism

    # The stack mount should not be flagged
    assert all('/opt/stacks' not in w for w in warns)
    assert '/opt/stacks' not in mism
