"""API routes package for app.routes.api.

This package exposes the API blueprint defined in `api_impl.py` so that
existing imports like `from app.routes import api` and `app.register_blueprint(api.bp)`
continue to work after converting `app/routes/api` to a package.
"""
from .api_impl import bp

# Re-export commonly used names (if other modules expect them)
__all__ = ["bp"]
