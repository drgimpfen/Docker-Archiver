import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.stacks import _is_ignored_destination


def test_filter_system_and_overlay_paths():
    assert _is_ignored_destination('/var/lib/some')
    assert _is_ignored_destination('/etc/hosts')
    assert _is_ignored_destination('/usr/local/bin')
    assert _is_ignored_destination('/proc/1')
    assert _is_ignored_destination('/sys/fs')
    assert _is_ignored_destination('/archives')
    assert _is_ignored_destination('/var/run/docker.sock')
    assert _is_ignored_destination('/')
    # overlay source should be ignored
    assert _is_ignored_destination('/opt/foo', 'overlay')

def test_include_stack_path():
    assert not _is_ignored_destination('/opt/stacks')
    assert not _is_ignored_destination('/home/user/docker')

# explicit ignored tmp downloads
def test_tmp_downloads_ignored():
    assert _is_ignored_destination('/tmp/downloads')
