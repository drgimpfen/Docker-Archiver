import io
import json
import time
from app.executor import ArchiveExecutor

class DummyExecutor(ArchiveExecutor):
    def __init__(self):
        super().__init__({'name':'test'}, is_dry_run=False)
        self.job_id = 1
        self.log_buffer = []
    def log(self, level, msg):
        self.log_buffer.append((level, msg))


def test_inactivity_timeout_preserves_partial_output(monkeypatch, tmp_path):
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: flaky:test\n''')

    # Simulate config and up
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode=0, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        if 'config' in cmd:
            return R(0, json.dumps({'services': {'app': {'image': 'flaky:test'}}}), '')
        if 'up' in cmd:
            return R(0, '', '')
        return R(0, '', '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Fake Popen that emits one line then stalls (no more output)
    class FakePopenPartial:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('Downloaded 10MB/50MB\n')
            self.stderr = io.StringIO('')
            self._killed = False
            self.returncode = None
        def poll(self):
            return None if not self._killed else 0
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self._killed = True
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopenPartial)

    # Ensure docker.from_env works (images will still be considered missing until pull recorded)
    class DummyImages:
        def get(self, name):
            # After pull is attempted, the fake Popen has output but we don't change docker state here
            raise Exception('not found')
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Set policy ALWAYS and small inactivity timeout
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always' if k=='image_pull_policy' else ('1' if k=='image_pull_inactivity_timeout' else d))

    # Monkeypatch time.time to simulate passage of time
    t = {'v': 1000}
    def fake_time():
        t['v'] += 2
        return t['v']
    monkeypatch.setattr('time.time', fake_time)

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    # Pull should have timed out due to inactivity
    assert res is False
    # Partial output should be preserved in stack_image_updates
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'Downloaded 10MB/50MB' in ex.stack_image_updates['teststack']['pull_output']
    assert any('inactivity' in m for _, m in ex.log_buffer)
