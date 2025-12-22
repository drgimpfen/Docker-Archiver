import tempfile
import os
from pathlib import Path
from app.utils import apply_permissions_recursive


def test_apply_permissions_writes_report_and_returns_keys(tmp_path):
    # Create a temporary base directory and a test file
    base = tmp_path / "archives"
    base.mkdir()
    (base / "testdir").mkdir()
    (base / "testdir" / "file1.txt").write_text("hello")

    # Create a temp report file
    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', prefix='test_permissions_report_', mode='r+', encoding='utf-8')
    tf_name = tf.name
    tf.close()

    try:
        res = apply_permissions_recursive(str(base), collect_list=False, report_path=tf_name)

        # Result contains expected keys
        assert 'files_changed' in res
        assert 'dirs_changed' in res
        assert 'errors' in res
        assert 'fixed_files' in res and isinstance(res['fixed_files'], list)
        assert 'fixed_dirs' in res and isinstance(res['fixed_dirs'], list)
        assert res.get('report_path') == tf_name

        # Report file exists and contains header and completion line
        with open(tf_name, 'r', encoding='utf-8') as rf:
            content = rf.read()
        assert '# Permissions fix report for base' in content
        assert '# Completed: files_changed=' in content

    finally:
        try:
            os.unlink(tf_name)
        except Exception:
            pass
