"""Package shim for notifications.

This module re-exports the public symbols from `core.py` so existing imports
such as `from app.notifications import send_archive_notification` continue to
work while the codebase is migrated to a package layout.
"""

from .core import *  # re-export everything (keeps compatibility during refactor)
from .formatters import strip_html_tags, build_compact_text, split_section_by_length

__all__ = [
    name for name in dir() if not name.startswith('_')
]
