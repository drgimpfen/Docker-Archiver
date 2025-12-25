import os
import json
import tempfile
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

    # Ensure setting disallows pull
    monkeypatch.setattr('app.executor.get_setting', lambda k, d='': 'false')

    ex = DummyExecutor()
    res = ex._start_stack('teststack', compose_file)
    assert res == 'skipped'
    # Check that a warning was logged
    assert any('Skipped starting stack' in m for _, m in ex.log_buffer)
