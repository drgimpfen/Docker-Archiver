from app.notifications.adapters.generic import _notify_with_retry


class FakeAp:
    def notify(self, **kwargs):
        # Simulate an Apprise plugin that logs debug about the response
        import apprise
        apprise.logger.debug("Response Details:\n{'error':'unsupported_parameter','detail':'field X is not supported'}")
        return False


def test_notify_captures_apprise_debug_logs():
    apobj = FakeAp()
    ok, detail = _notify_with_retry(apobj, title='t', body='b')
    assert not ok
    assert detail is not None
    assert 'Response Details' in detail or 'unsupported_parameter' in detail
