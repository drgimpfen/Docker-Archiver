# PR: Refactor notifications module into modular components ✅

## Summary
**What:** Split the monolithic `app/notifications` implementation into small, focused modules and removed the legacy `core.py` compatibility layer.

**Why:** Improve maintainability, testability, and readability. Reduce file size and isolate responsibilities (helpers, formatting, sending, handlers).

**Files added / updated**
- **Added / updated**:
  - `app/notifications/helpers.py` — pure helper functions (`get_setting`, `get_user_emails`, `get_notification_format`, `should_notify`, etc.)
  - `app/notifications/sender.py` — centralized `send_email` logic (attachment handling, formatting)
  - `app/notifications/handlers.py` — notification handlers (`send_archive_notification`, `send_archive_failure_notification`, `send_retention_notification`, `send_error_notification`, `send_test_notification`, `send_permissions_fix_notification`)
  - `app/notifications/__init__.py` — removed; imports updated to use concrete submodules (`helpers`, `handlers`, `formatters`, `sender`)
  - Tests updated to reference concrete submodules (e.g., `app.notifications.handlers`, `app.notifications.helpers`)
- **Removed**:
  - `app/notifications/core.py` — removed legacy compatibility file after migrating imports and tests

## Behavior / Compatibility
- Package-level shim removed; imports were updated across the codebase to use concrete submodules (e.g., `from app.notifications.handlers import send_archive_notification`).
- Tests that previously patched `app.notifications.core` were updated to patch concrete modules (e.g., `app.notifications.handlers`, `app.notifications.helpers`).

## Testing & Verification
- Unit tests updated: replaced `monkeypatch.setattr('app.notifications.core.*', ...)` with `monkeypatch.setattr('app.notifications.*', ...)` in affected test files:
  - `tests/test_smtp_adapter.py`
  - `tests/test_send_test_notification.py`
  - `tests/test_send_link_existing_archive.py`
  - `tests/test_notifications_pull_excerpt.py`
- Suggested commands to run:
  - `python -m pytest -q` (run test suite)
  - `python -m pytest tests/test_smtp_adapter.py -q` (smoke test for SMTP adapter)
  - `flake8` / `pylint` (linting)

## Notes for reviewers ✅
- Pay attention to differences in sending behavior; the `sender.send_email` centralizes the SMTP logic and should preserve previous semantics.
- Verify that `SMTPAdapter` integrations still work; adapter imports were changed to use `app.notifications` helpers.
- Confirm monkeypatch/fixture updates in tests; no semantic change intended.

## Suggested PR Description (copy-paste)
```
Refactor: modularize notifications package

- Extract helpers to `app/notifications/helpers.py`
- Extract sending logic to `app/notifications/sender.py`
- Move all notification handlers to `app/notifications/handlers.py`
- Update `app/notifications/__init__.py` to re-export public symbols
- Update tests to reference `app.notifications` (remove reliance on `core.py`)
- Remove `app/notifications/core.py` legacy shim

This keeps behavior unchanged while making the codebase easier to maintain and test.
```

## Checklist (for PR)
- [ ] All tests passing locally
- [ ] Linting and static checks passed
- [ ] Update changelog (if applicable)
- [ ] Add a short entry in `DEPLOY.md` or `README.md` if needed (not required for internal refactor)

---

Saved to: `PR_NOTIFICATIONS_REFACTOR.md`

If you want, I can also open a draft PR branch and create the PR message on GitHub (requires Git remote access / credentials).