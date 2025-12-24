"""DEPRECATED

This module was split into smaller modules under `app.routes.api`:
- `jobs.py` (job listing, logs, tail)
- `downloads.py` (download token generation and folder prep)
- `cleanup.py` (cleanup runner)
- `sse.py` (SSE endpoints)

Keep this module as a small shim for backwards compatibility: importing it will import the new modules and register their routes.
"""

# Import package `bp` and submodules so routes are registered when this module is imported
from app.routes.api import bp  # noqa: F401
from app.routes.api import jobs, cleanup, sse  # noqa: F401

# Nothing else here — the concrete implementations live in the submodules now.
