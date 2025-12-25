import os
import json
import tempfile
import subprocess
from app.executor import ArchiveExecutor

class DummyExecutor(ArchiveExecutor):
    def __init__(self):
        super().__init__({'name':'test'}, is_dry_run=False)
        self.job_id = 1
        self.log_buffer = []
    def log(self, level, msg):
        # capture logs for assertions
        self.log_buffer.append((level, msg))


def test_start_stack_skips_when_images_missing_and_no_pull(monkeypatch, tmp_path):
    # Create dummy compose file
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: nonexistent:test\n''')
    # Monkeypatch subprocess.run to return a fake config JSON listing the image
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode, stdout):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = ''
        if 'config' in cmd:
            # return json structure
            out = json.dumps({'services': {'app': {'image': 'nonexistent:test'}}})
            return R(0, out)
        return R(0, '')
    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch docker SDK to raise on image get
    class DummyImages:
        def get(self, name):
            raise Exception('not found')
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure setting disallows pull (policy 'never')
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'never')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res == 'skipped'
    # Check that a warning was logged
    assert any('Skipped starting stack' in m for _, m in ex.log_buffer)


def test_start_stack_uses_no_pull_flag_when_pulls_disabled_and_supported(monkeypatch, tmp_path):
    # Create dummy compose file
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    # Monkeypatch subprocess.run to simulate 'config' and 'up --help' and capture 'up' invocation
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            out = json.dumps({'services': {'app': {'image': 'present:test'}}})
            return R(0, out)
        if '--help' in cmd:
            # Advertise --pull support
            return R(0, '--pull')
        if 'up' in cmd:
            # Simulate successful up
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch docker SDK to succeed on image get
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure setting disallows pull (policy 'never')
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'never')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is True
    # Find the 'up' invocation and ensure '--pull=never' is present
    up_calls = [c for c in calls if 'up' in c]
    assert any('--pull=never' in ' '.join(c) for c in up_calls)


def test_start_stack_always_pulls_before_start(monkeypatch, tmp_path):
    # Create dummy compose file
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    # Monkeypatch subprocess.run to capture config, help and up invocations
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            out = json.dumps({'services': {'app': {'image': 'present:test'}}})
            return R(0, out)
        if '--help' in cmd:
            # Simulate no pull flag advertised
            return R(0, '')
        if 'up' in cmd:
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch subprocess.Popen to simulate pull streaming
    import io
    class FakePopen:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.returncode = 0
            # Simulate some stdout and stderr output lines
            self.stdout = io.StringIO('Downloaded newer image foo:latest\n')
            self.stderr = io.StringIO('')
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopen)

    # Monkeypatch docker SDK to succeed on image get
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure policy ALWAYS
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is True
    # Ensure 'pull' was invoked via Popen
    # (we don't track calls to Popen easily here, but we can assert pull output was recorded)
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'Downloaded newer image' in ex.stack_image_updates['teststack']['pull_output']
    assert 'Container images pulled' in '\n'.join(ex.log_buffer) or 'Pull output' in '\n'.join(ex.log_buffer)


def test_never_uses_up_pull_flag_even_on_failure(monkeypatch, tmp_path):
    # Ensure we never add --pull=always to 'docker compose up', even if explicit pull failed
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode=0, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            return R(0, json.dumps({'services': {'app': {'image': 'present:test'}}}), '')
        if '--help' in cmd:
            return R(0, '--pull')
        if 'up' in cmd:
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Fake Popen that simulates a failed pull (non-zero returncode)
    import io
    class FakePopenFailed:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('Some output\n')
            self.stderr = io.StringIO('pull failed\n')
            self.returncode = 1
        def poll(self):
            return self.returncode
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopenFailed)

    # Ensure docker.from_env works
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure policy ALWAYS
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is False
    up_calls = [c for c in calls if 'up' in c]
    assert all('--pull=always' not in ' '.join(c) for c in up_calls)
    # Ensure partial pull output recorded
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'pull failed' in ex.stack_image_updates['teststack']['pull_output']


def test_pull_timeout_setting_is_forwarded(monkeypatch, tmp_path):
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    # Capture run calls for config/help/up
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode=0, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append({'cmd': cmd, 'timeout': timeout})
        if 'config' in cmd:
            out = json.dumps({'services': {'app': {'image': 'present:test'}}})
            return R(0, out)
        if '--help' in cmd:
            return R(0, '')
        if 'up' in cmd:
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch subprocess.Popen to capture wait timeout
    import io
    wait_time = {}
    class FakePopen:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('')
            self.stderr = io.StringIO('')
            self.returncode = 0
        def wait(self, timeout=None):
            wait_time['timeout'] = timeout
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopen)

    # Ensure docker.from_env works
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Set policy ALWAYS and custom inactivity timeout
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always' if k=='image_pull_policy' else ('37' if k=='image_pull_inactivity_timeout' else d))

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is True
    # Find the pull wait timeout and ensure it equals 37
    assert wait_time.get('timeout') == 37


def test_inactivity_timeout_logs_message_when_no_activity(monkeypatch, tmp_path):
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    # Simulate config and up commands
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode=0, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        if 'config' in cmd:
            return R(0, json.dumps({'services': {'app': {'image': 'present:test'}}}), '')
        if 'up' in cmd:
            return R(0, '', '')
        return R(0, '', '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Fake Popen that produces no output and doesn't exit on its own
    import io
    class FakePopenNoOutput:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('')
            self.stderr = io.StringIO('')
            self._killed = False
            self.returncode = None
        def poll(self):
            return None if not self._killed else (1)
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self._killed = True
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopenNoOutput)

    # Ensure docker.from_env works
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Set policy ALWAYS and small inactivity timeout
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always' if k=='image_pull_policy' else ('1' if k=='image_pull_inactivity_timeout' else d))

    # Monkeypatch time.time to simulate passage of time (first call sets last_activity, subsequent calls advance beyond threshold)
    t = {'v': 1000}
    def fake_time():
        # Advance time by 2s each call so inactivity threshold of 1s is exceeded quickly
        t['v'] += 2
        return t['v']
    monkeypatch.setattr('time.time', fake_time)

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is False
    assert any('Image pull timed out after' in m and 'inactivity' in m for _, m in ex.log_buffer)


def test_start_stack_avoids_duplicate_pull_when_supported_and_explicit_pull(monkeypatch, tmp_path):
    # Create dummy compose file
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    # Monkeypatch subprocess.run to simulate 'config' and 'up --help' that advertises --pull
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            out = json.dumps({'services': {'app': {'image': 'present:test'}}})
            return R(0, out)
        if '--help' in cmd:
            # Advertise --pull support
            return R(0, '--pull')
        if 'up' in cmd:
            # Simulate successful up
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch subprocess.Popen to simulate a successful explicit pull
    import io
    class FakePopen:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('')
            self.stderr = io.StringIO('')
            self.returncode = 0
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopen)

    # Monkeypatch docker SDK to succeed on image get
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure policy ALWAYS
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is True
    # Ensure explicit 'pull' was invoked (we simulate it via Popen)
    # Ensure the 'up' invocation does not include '--pull=always' to avoid duplicate pulls
    up_calls = [c for c in calls if 'up' in c]
    assert all('--pull=always' not in ' '.join(c) for c in up_calls)
    # Ensure executor recorded pull output and logged update message
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'Container images pulled' in '\n'.join(ex.log_buffer) or 'Pull output' in '\n'.join(ex.log_buffer)


def test_missing_policy_pulls_and_records_output(monkeypatch, tmp_path):
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: flaky:test\n''')

    calls = []
    # Simulate config; pull will be performed via Popen; up via run
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            out = json.dumps({'services': {'app': {'image': 'flaky:test'}}})
            return R(0, out)
        if 'up' in cmd:
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Monkeypatch subprocess.Popen to simulate pull output
    import io
    class FakePopen:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('Downloaded newer image for flaky:test\n')
            self.stderr = io.StringIO('')
            self.returncode = 0
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopen)

    # Make docker.from_env.get raise initially, then succeed after pull
    state = {'pulled': False}
    class DummyImages:
        def get(self, name):
            if not state['pulled']:
                raise Exception('not found')
            return True
    class DummyClient:
        images = DummyImages()
    # Monkeypatch docker.from_env to flip state when pull is invoked
    def fake_from_env():
        # When 'pull' command ran, mark pulled True by scanning calls and also check Popen invocations
        if any('pull' in c for c in calls):
            state['pulled'] = True
        return DummyClient()

    monkeypatch.setattr('docker.from_env', fake_from_env)

    # Set policy to 'missing'
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'missing')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is True
    # Confirm pull was attempted (Popen used) and recorded
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'Downloaded newer image' in ex.stack_image_updates['teststack']['pull_output']


def test_explicit_pull_failure_aborts_and_no_up_or_flag(monkeypatch, tmp_path):
    compose_file = tmp_path / 'docker-compose.yml'
    compose_file.write_text('''version: "3.8"\nservices:\n  app:\n    image: present:test\n''')

    calls = []
    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        class R:
            def __init__(self, returncode=0, stdout='', stderr=''):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        calls.append(cmd)
        if 'config' in cmd:
            return R(0, json.dumps({'services': {'app': {'image': 'present:test'}}}), '')
        if 'up' in cmd:
            # If 'up' is invoked it should not contain a pull flag when an explicit pull failed
            return R(0, '')
        return R(0, '')

    monkeypatch.setattr('subprocess.run', fake_run)

    # Fake Popen that simulates a failed pull (non-zero returncode)
    import io
    class FakePopenFailed:
        def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
            self.cmd = cmd
            self.stdout = io.StringIO('Some output\n')
            self.stderr = io.StringIO('pull failed\n')
            self.returncode = 1
        def poll(self):
            return self.returncode
        def wait(self, timeout=None):
            return 0
        def kill(self):
            self.returncode = 1
    monkeypatch.setattr('subprocess.Popen', FakePopenFailed)

    # Ensure docker.from_env works
    class DummyImages:
        def get(self, name):
            return True
    class DummyClient:
        images = DummyImages()
    monkeypatch.setattr('docker.from_env', lambda: DummyClient())

    # Ensure policy ALWAYS
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'always')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res is False
    # Ensure we did not attempt to start the stack (no 'up' command in calls)
    assert not any('up' in c for c in calls)
    # Ensure pull output (partial) was recorded
    assert hasattr(ex, 'stack_image_updates') and 'teststack' in ex.stack_image_updates
    assert 'pull failed' in ex.stack_image_updates['teststack']['pull_output']

