"""
Settings routes.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.auth import login_required, get_current_user
from app.db import get_db
from app.scheduler import reload_schedules
from app.notifications import send_test_notification


bp = Blueprint('settings', __name__, url_prefix='/settings')


@bp.route('/', methods=['GET', 'POST'])
@login_required
def manage_settings():
    """Settings page."""
    if request.method == 'POST':
        try:
            # Update settings
            base_url = request.form.get('base_url', 'http://localhost:8080')
            apprise_urls = request.form.get('apprise_urls', '')
            notify_success = request.form.get('notify_success') == 'on'
            notify_error = request.form.get('notify_error') == 'on'
            maintenance_mode = request.form.get('maintenance_mode') == 'on'
            max_token_downloads = request.form.get('max_token_downloads', '3')
            
            # Cleanup settings
            cleanup_enabled = request.form.get('cleanup_enabled') == 'on'
            cleanup_time = request.form.get('cleanup_time', '02:30')
            cleanup_log_retention_days = request.form.get('cleanup_log_retention_days', '90')
            cleanup_dry_run = request.form.get('cleanup_dry_run') == 'on'
            notify_cleanup = request.form.get('notify_cleanup') == 'on'
            
            # Validate cleanup time format
            if cleanup_enabled:
                try:
                    hour, minute = map(int, cleanup_time.split(':'))
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        raise ValueError
                except (ValueError, AttributeError):
                    flash('Invalid cleanup time format. Please use HH:MM format (e.g., 02:30).', 'danger')
                    return redirect(url_for('settings.manage_settings'))
            
            with get_db() as conn:
                cur = conn.cursor()
                settings_to_update = [
                    ('base_url', base_url),
                    ('apprise_urls', apprise_urls),
                    ('notify_on_success', 'true' if notify_success else 'false'),
                    ('notify_on_error', 'true' if notify_error else 'false'),
                    ('maintenance_mode', 'true' if maintenance_mode else 'false'),
                    ('max_token_downloads', max_token_downloads),
                    ('cleanup_enabled', 'true' if cleanup_enabled else 'false'),
                    ('cleanup_time', cleanup_time),
                    ('cleanup_log_retention_days', cleanup_log_retention_days),
                    ('cleanup_dry_run', 'true' if cleanup_dry_run else 'false'),
                    ('notify_on_cleanup', 'true' if notify_cleanup else 'false'),
                ]
                
                for key, value in settings_to_update:
                    cur.execute("""
                        INSERT INTO settings (key, value) VALUES (%s, %s)
                        ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP;
                    """, (key, value, value))
                
                conn.commit()
            
            # Reload scheduler if maintenance mode changed
            reload_schedules()
            
            # Reschedule cleanup task if settings changed
            from app.scheduler import schedule_cleanup_task
            schedule_cleanup_task()
            
            flash('Settings saved successfully!', 'success')
            return redirect(url_for('settings.manage_settings'))
            
        except Exception as e:
            flash(f'Error saving settings: {e}', 'danger')
    
    # Load current settings
    settings_dict = {}
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings;")
        for row in cur.fetchall():
            settings_dict[row['key']] = row['value']
    
    return render_template(
        'settings.html',
        settings=settings_dict,
        current_user=get_current_user()
    )


@bp.route('/test-notification', methods=['POST'])
@login_required
def test_notification():
    """Send a test notification."""
    try:
        send_test_notification()
        return jsonify({'success': True, 'message': 'Test notification sent successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to send notification: {str(e)}'}), 500
