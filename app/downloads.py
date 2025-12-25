"""DEPRECATED: download token utilities removed.

The helper functions for token management, gradual regeneration, and temporary
archive creation were removed as part of deprecating the token-based download
flow. Keep this module as a harmless stub to ease transitional changes.
"""

# Downloads implementation removed. If you still import this module, consider
# updating your code to the new download strategy (pre-signed URLs / direct serving).

__all__ = []



# All token-related implementation has been removed from this module. The module
# now only exposes stub helpers above that raise runtime errors if used. If you
# need to reintroduce downloads, consider implementing a safer flow using
# pre-signed URLs or X-Accel-Redirect rather than keeping token state in the DB.

__all__ = []

