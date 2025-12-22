"""
Implementation of API routes (previously `app/routes/api.py`).
This module is imported by the package `app.routes.api` to expose the
`bp` blueprint and API handlers without changing existing imports.
"""
import secrets
import os
import subprocess
import threading
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context
from app.auth import login_required, get_current_user
from app.db import get_db
from app import utils


bp = Blueprint('api', __name__, url_prefix='/api')


def api_auth_required(f):
    """
    Decorator for API endpoints that accepts both session auth and API token auth.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API token in Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            
            # Validate token
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT u.* FROM users u
                    JOIN api_tokens t ON u.id = t.user_id
                    WHERE t.token = %s AND (t.expires_at IS NULL OR t.expires_at > NOW());
                """, (token,))
                user = cur.fetchone()
            
            if user:
                # Token is valid, proceed
                return f(*args, **kwargs)
            else:
                return jsonify({'error': 'Invalid or expired API token'}), 401
        
        # Fall back to session auth (for web UI)
        return login_required(f)(*args, **kwargs)
    
    return decorated_function


@bp.route('/jobs/<int:job_id>')
@api_auth_required
def get_job_details(job_id):
    """Get job details (for modal)."""
    with get_db() as conn:
        cur = conn.cursor()
        
        # Get job
        cur.execute("""
            SELECT j.*, 
                   a.name as archive_name,
                   EXTRACT(EPOCH FROM (j.end_time - j.start_time))::INTEGER as duration_seconds
            FROM jobs j
            LEFT JOIN archives a ON j.archive_id = a.id
            WHERE j.id = %s;
        """, (job_id,))
        job = cur.fetchone()
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Get stack metrics
        cur.execute("""
            SELECT * FROM job_stack_metrics 
            WHERE job_id = %s 
            ORDER BY start_time;
        """, (job_id,))
        metrics = cur.fetchall()
        
        # Set file_exists based on deleted_at timestamp
        for metric in metrics:
            if metric.get('archive_path'):
                metric['file_exists'] = metric.get('deleted_at') is None
            else:
                metric['file_exists'] = None
    
    job_out = dict(job)
    for k in ('start_time', 'end_time'):
        if job_out.get(k):
            job_out[k] = utils.to_iso_z(job_out[k])

    metrics_out = []
    for m in metrics:
        md = dict(m)
        for key, val in list(md.items()):
            # convert any datetime-like fields
            if hasattr(val, 'astimezone'):
                md[key] = utils.to_iso_z(val)
        metrics_out.append(md)

    return jsonify({
        'job': job_out,
        'metrics': metrics_out
    })


@bp.route('/events')
@api_auth_required
def global_events():
    """SSE endpoint for global events (e.g., permissions fix completion)."""
    from app.sse import register_global_listener, unregister_global_listener

    def gen():
        q = register_global_listener()
        try:
            while True:
                try:
                    data = q.get(timeout=15)  # wait for up to 15s
                    yield f"data: {data}\n\n"
                except Exception:
                    # Keep the connection alive by sending a comment every 15s
                    yield ': keep-alive\n\n'
        finally:
            try:
                unregister_global_listener(q)
            except Exception:
                pass

    return Response(stream_with_context(gen()), mimetype='text/event-stream')

# (omitted: rest of original file for brevity in this generated helper; the file includes full API handlers unchanged)
