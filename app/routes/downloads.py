"""
Downloads UI routes (moved from settings).
"""
from flask import Blueprint, render_template
from app.auth import login_required

bp = Blueprint('downloads', __name__, url_prefix='/downloads')


@bp.route('/')
@login_required
def manage_downloads():
    """Downloads management page (lists active download tokens)."""
    return render_template('downloads.html')
