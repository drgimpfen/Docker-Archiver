"""
Legacy redirects for the old `/archives` routes.
This module provides minimal redirect handlers to preserve backward
compatibility with clients that post to `/archives/*`.
"""
from flask import Blueprint, redirect, url_for
from app.auth import login_required

legacy_bp = Blueprint('archives_legacy', __name__, url_prefix='/archives')

@legacy_bp.route('/', methods=['GET'])
@login_required
def legacy_index():
    """Redirect legacy archive UI path to the Dashboard (UI was removed)."""
    return redirect(url_for('dashboard.index'))

# Preserve POST behavior via 307 redirects to the new API endpoints (preserves method)
@legacy_bp.route('/create', methods=['POST'])
@login_required
def legacy_create():
    return redirect(url_for('archives.create'), code=307)

@legacy_bp.route('/<int:archive_id>/edit', methods=['POST'])
@login_required
def legacy_edit(archive_id):
    return redirect(url_for('archives.edit', archive_id=archive_id), code=307)

@legacy_bp.route('/<int:archive_id>/delete', methods=['POST'])
@login_required
def legacy_delete(archive_id):
    return redirect(url_for('archives.delete', archive_id=archive_id), code=307)

@legacy_bp.route('/<int:archive_id>/retention', methods=['POST'])
@login_required
def legacy_retention(archive_id):
    return redirect(url_for('archives.run_retention_only', archive_id=archive_id), code=307)
