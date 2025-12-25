"""
Notification handlers for different job types.
"""
import os
from app.db import get_db
from app.utils import format_bytes, format_duration, get_archives_path, get_logger
from app.notifications.helpers import get_setting, get_user_emails, get_subject_with_tag, should_notify
from app.notifications.formatters import build_full_body, build_compact_text, build_sections
from app.notifications.sender import send_email

logger = get_logger(__name__)


def send_archive_failure_notification(archive_config, job_id, stack_metrics, duration, total_size):
    """Send notification for an archive job failure."""
    try:
        logger.info("Notifications: send_archive_failure_notification called for archive=%s job=%s", archive_config.get('name') if archive_config else None, job_id)
    except Exception:
        pass

    if not should_notify('error'):
        return
    
    try:
        base_url = get_setting('base_url', 'http://localhost:8080')
        
        # Build notification message (failure)
        archive_name = archive_config['name']
        stack_count = len(stack_metrics)
        success_count = sum(1 for m in stack_metrics if m['status'] == 'success')
        failed_count = stack_count - success_count
        
        size_str = format_bytes(total_size)
        duration_min = duration // 60
        duration_sec = duration % 60
        duration_str = f"{duration_min}m {duration_sec}s" if duration_min > 0 else f"{duration_sec}s"
        
        status_emoji = "✖️"
        title = get_subject_with_tag(f"{status_emoji} Archive Failed: {archive_name}")
        
        # Check if any stacks have named volumes
        stacks_with_volumes = [m for m in stack_metrics if m.get('named_volumes')]
        
        # Created archives table (alphabetical by filename)
        created_archives = []
        for m in stack_metrics:
            path = m.get('archive_path')
            size = m.get('archive_size_bytes') or 0
            if path:
                created_archives.append({'path': str(path), 'size': size})

        # Fetch job retention/log info
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT reclaimed_bytes, log FROM jobs WHERE id = %s;", (job_id,))
                job_row = cur.fetchone()
                reclaimed = job_row.get('reclaimed_bytes') if job_row else None
                job_log = job_row.get('log') if job_row else ''
        except Exception:
            reclaimed = None
            job_log = ''

        # Build HTML body using helpers
        body = build_full_body(
            archive_name=archive_name,
            status_emoji=status_emoji,
            success_count=success_count,
            stack_count=stack_count,
            size_str=size_str,
            duration_str=duration_str,
            stack_metrics=stack_metrics,
            created_archives=created_archives,
            total_size=total_size,
            reclaimed=reclaimed,
            job_log=job_log,
            base_url=base_url,
            stacks_with_volumes=stacks_with_volumes,
            job_id=job_id,
            include_log_inline=True,
        )

        # user settings for attachments
        attach_log_setting = get_setting('notify_attach_log', 'false').lower() == 'true'
        attach_on_failure_setting = get_setting('notify_attach_log_on_failure', 'false').lower() == 'true'

        # Always build full HTML body for emails and a structured sections list for chat services
        should_attach_log = attach_log_setting or (attach_on_failure_setting and failed_count > 0)
        html_body_to_send = body

        # Ensure skipped note is present in the body used for email (attachment mode may recreate body)
        try:
            skipped = [s for s in (stack_metrics or []) if s.get('status') == 'skipped']
            if skipped:
                note_html = "\n<hr>\n<p><strong>Note:</strong> Some stacks were <em>skipped</em> during restart because required images were not available locally and image pulls are disabled in the application settings. See <a href=\"https://github.com/drgimpfen/Docker-Archiver#image-pull-policy\">README</a> for details.</p>\n<ul>\n"
                for s in skipped:
                    err = s.get('error') or 'Skipped (missing images)'
                    note_html += f"  <li><strong>{s.get('stack_name')}</strong>: {err}</li>\n"
                note_html += "</ul>\n"
                html_body_to_send = (html_body_to_send or '') + note_html
        except Exception:
            pass

        # If any stacks had images pulled/updated, add a short note to the HTML body
        try:
            updated = [s for s in (stack_metrics or []) if s.get('images_pulled')]
            if updated:
                # Always show the full filtered pull output inline in notifications
                excerpt_lines = 0

                note_html = "\n<hr>\n<p><strong>Note:</strong> Some stacks had container images pulled during this job; please verify containers were updated as expected. See <a href=\"https://github.com/drgimpfen/Docker-Archiver#image-pull-policy\">README</a> for details.</p>\n<ul>\n"
                for s in updated:
                    stack_name = s.get('stack_name')
                    pull_output = (s.get('pull_output') or '')
                    if pull_output:
                        # Normalize and strip ANSI sequences
                        import re as _re, html as _html
                        ansi_re = _re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
                        raw = str(pull_output)
                        norm = ansi_re.sub('', raw)

                        # Split into lines and filter out transient progress updates.
                        # Heuristics tuned to keep final, meaningful lines (e.g., 'Pulled', 'Download complete', 'Already exists')
                        # and to remove transient progress like spinners and per-layer live percentages.
                        filtered = []
                        for line in raw.splitlines():
                            # Remove any remaining ANSI escapes early
                            clean = ansi_re.sub('', line).rstrip()
                            if not clean:
                                continue

                            # If line contains a carriage return it's likely an in-place progress update -> skip
                            if '\r' in line:
                                continue

                            # Trim whitespace for checks
                            s = clean.strip()
                            if not s:
                                continue

                            # Keep top-level summary lines like "[+] Pulling 15/15"
                            if _re.match(r'^\s*\[\+\]\s*Pulling', s, _re.IGNORECASE):
                                filtered.append(s)
                                continue

                            # Keep lines that start with a checkmark (✔) — they indicate completed steps
                            if s.startswith('✔') or s.startswith('\u2713'):
                                filtered.append(s)
                                continue

                            # Keep lines indicating completion or important info
                            if _re.search(r'\b(Pulled|Downloaded|Downloaded newer image|Download complete|Already exists|Digest:|sha256:)\b', s, _re.IGNORECASE):
                                filtered.append(s)
                                continue

                            # Skip obvious progress lines that contain MB/MB, progress blocks or percentage
                            if _re.search(r"\d+(?:\.\d+)?M[Bb]?/\d+(?:\.\d+)?M[Bb]?", s):
                                continue
                            if _re.search(r'^\s*\d+%\b', s):
                                continue

                            # Skip lines with spinner symbols (common Unicode spinner glyphs)
                            if any(ch in s for ch in ['⠹', '⠏', '⠸', '⠼', '⠴', '⠦', '⠧']):
                                continue

                            # Skip lines with generic progress verbs unless they explicitly denote completion
                            if _re.search(r'\b(Downloading|Pulling|Extracting|Compressing|Verifying|Waiting|Pushing)\b', s, _re.IGNORECASE):
                                continue

                            # If we reach here, the line didn't match any keep/skip rule; keep it as potentially useful
                            filtered.append(s)

                        # Determine excerpt: 0 -> unlimited (all filtered lines), otherwise first N
                        if excerpt_lines == 0:
                            excerpt = '\n'.join(filtered)
                            excerpt_label = 'full (filtered)'
                        else:
                            excerpt = '\n'.join(filtered[:excerpt_lines])
                            excerpt_label = f'first {excerpt_lines} lines (filtered)'

                        escaped = _html.escape(excerpt)
                        note_html += f"  <li><strong>{stack_name}</strong>: Pull output (excerpt, {excerpt_label}):<br>\n    <pre style='background:#f7f7f7;padding:8px;border-radius:5px;white-space:pre-wrap;overflow:auto;max-height:240px;'>{escaped}</pre></li>\n"
                    else:
                        note_html += f"  <li><strong>{stack_name}</strong>: Pull output available in job log</li>\n"
                note_html += "</ul>\n"
                html_body_to_send = (html_body_to_send or '') + note_html
                # Also append to inline body so recipients see it regardless
                body = (body or '') + note_html
        except Exception:
            pass
    except Exception:
        pass

    # Prepare attachment if needed
    attach_path = None
    temp_files = []
    try:
        job_log_text = None
        try:
            job_log_text = job_row.get('log') if job_row else None
        except Exception:
            job_log_text = None

        if job_log_text and should_attach_log:
            import tempfile, time
            from app.utils import filename_safe, filename_timestamp
            temp_dir = tempfile.gettempdir()
            if archive_name:
                safe_archive = filename_safe(archive_name)[:40]
                filename_core = f'job_{job_id}_{safe_archive}_{filename_timestamp()}'
            else:
                filename_core = f'job_{job_id}_{filename_timestamp()}'
            attach_path = os.path.join(temp_dir, f"{filename_core}.log")
            if os.path.exists(attach_path):
                attach_path = os.path.join(temp_dir, f'{filename_core}_{int(time.time())}.log')
            try:
                with open(attach_path, 'w', encoding='utf-8') as f:
                    f.write(job_log_text)
                temp_files.append(attach_path)
            except Exception:
                attach_path = None
    except Exception as e:
        logger.exception("Failed to prepare job log attachment for email: %s", e)

    # Send email
    send_email(title, html_body_to_send, attach=attach_path, context=f'email_smtp_{archive_name}_{job_id}')


def send_archive_notification(archive_config, job_id, stack_metrics, duration, total_size):
    """Send notification for a successful archive job."""
    try:
        logger.info("Notifications: send_archive_notification called for archive=%s job=%s", archive_config.get('name') if archive_config else None, job_id)
    except Exception:
        pass

    if not should_notify('success'):
        return

    try:
        base_url = get_setting('base_url', 'http://localhost:8080')

        archive_name = archive_config.get('name') if archive_config else 'Archive'
        stack_count = len(stack_metrics)
        success_count = sum(1 for m in stack_metrics if m.get('status') == 'success')
        failed_count = stack_count - success_count

        size_str = format_bytes(total_size)
        duration_min = duration // 60
        duration_sec = duration % 60
        duration_str = f"{duration_min}m {duration_sec}s" if duration_min > 0 else f"{duration_sec}s"

        status_emoji = "✅"
        title = get_subject_with_tag(f"{status_emoji} Archive Completed: {archive_name}")

        # Check if any stacks have named volumes
        stacks_with_volumes = [m for m in stack_metrics if m.get('named_volumes')]

        # Created archives table (alphabetical by filename)
        created_archives = []
        for m in stack_metrics:
            path = m.get('archive_path')
            size = m.get('archive_size_bytes') or 0
            if path:
                created_archives.append({'path': str(path), 'size': size})

        # Fetch job retention/log info
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT reclaimed_bytes, log FROM jobs WHERE id = %s;", (job_id,))
                job_row = cur.fetchone()
                reclaimed = job_row.get('reclaimed_bytes') if job_row else None
                job_log = job_row.get('log') if job_row else ''
        except Exception:
            reclaimed = None
            job_log = ''

        # Build HTML body using helpers
        body = build_full_body(
            archive_name=archive_name,
            status_emoji=status_emoji,
            success_count=success_count,
            stack_count=stack_count,
            size_str=size_str,
            duration_str=duration_str,
            stack_metrics=stack_metrics,
            created_archives=created_archives,
            total_size=total_size,
            reclaimed=reclaimed,
            job_log=job_log,
            base_url=base_url,
            stacks_with_volumes=stacks_with_volumes,
            job_id=job_id,
            include_log_inline=True,
        )

        # user settings for attachments
        attach_log_setting = get_setting('notify_attach_log', 'false').lower() == 'true'
        attach_on_failure_setting = get_setting('notify_attach_log_on_failure', 'false').lower() == 'true'

        # Always include log inline in the email body
        html_body_to_send = body

        # If any stacks had images pulled/updated, add the full filtered pull output inline
        try:
            updated = [s for s in (stack_metrics or []) if s.get('images_pulled')]
            if updated:
                note_html = "\n<hr>\n<p><strong>Note:</strong> The following stacks had images pulled during this job; please verify containers were updated as expected. See <a href=\"https://github.com/drgimpfen/Docker-Archiver#image-pull-policy\">README</a> for details.</p>\n<ul>\n"
                import re as _re, html as _html
                ansi_re = _re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
                for s in updated:
                    stack_name = s.get('stack_name')
                    pull_output = (s.get('pull_output') or '')
                    if pull_output:
                        raw = str(pull_output)
                        # Filter/normalize lines (same heuristics as failure notifier)
                        filtered = []
                        for line in raw.splitlines():
                            clean = ansi_re.sub('', line).rstrip()
                            if not clean:
                                continue
                            if '\r' in line:
                                continue
                            part = clean.strip()
                            if not part:
                                continue
                            if _re.match(r'^\s*\[\+\]\s*Pulling', part, _re.IGNORECASE):
                                filtered.append(part)
                                continue
                            if part.startswith('✔') or part.startswith('\u2713'):
                                filtered.append(part)
                                continue
                            if _re.search(r'\b(Pulled|Downloaded|Downloaded newer image|Download complete|Already exists|Digest:|sha256:)\b', part, _re.IGNORECASE):
                                filtered.append(part)
                                continue
                            if _re.search(r"\d+(?:\.\d+)?M[Bb]?/\d+(?:\.\d+)?M[Bb]?", part):
                                continue
                            if _re.search(r'^\s*\d+%\b', part):
                                continue
                            if any(ch in part for ch in ['⠹','⠏','⠸','⠼','⠴','⠦','⠧']):
                                continue
                            if _re.search(r'\b(Downloading|Pulling|Extracting|Compressing|Verifying|Waiting|Pushing)\b', part, _re.IGNORECASE):
                                continue
                            filtered.append(part)

                        excerpt = '\n'.join(filtered)
                        escaped = _html.escape(excerpt)
                        note_html += f"  <li><strong>{stack_name}</strong>: Pull output:<br>\n    <pre style='background:#f7f7f7;padding:8px;border-radius:5px;white-space:pre-wrap;overflow:auto;max-height:240px;'>{escaped}</pre></li>\n"
                    else:
                        note_html += f"  <li><strong>{stack_name}</strong>: Pull output available in job log</li>\n"
                note_html += "</ul>\n"
                html_body_to_send = (html_body_to_send or '') + note_html
                body = (body or '') + note_html
        except Exception:
            pass

        # Build compact text and sections (plain-text) for non-email services
        compact_text, lines = build_compact_text(archive_name, stack_metrics, created_archives, total_size, size_str, duration_str, stacks_with_volumes, reclaimed, base_url)
        sections = build_sections(archive_name, lines, created_archives, total_size, stack_metrics, stacks_with_volumes, reclaimed, base_url, job_id)

        # If any stacks were skipped due to missing images, add a short note to the HTML body
        try:
            skipped = [s for s in (stack_metrics or []) if s.get('status') == 'skipped']
            if skipped:
                note_html = "\n<hr>\n<p><strong>Note:</strong> Some stacks were <em>skipped</em> during restart because required images were not available locally and image pulls are disabled in the application settings. See <a href=\"https://github.com/drgimpfen/Docker-Archiver#image-pull-policy\">README</a> for details.</p>\n<ul>\n"
                for s in skipped:
                    err = s.get('error') or 'Skipped (missing images)'
                    note_html += f"  <li><strong>{s.get('stack_name')}</strong>: {err}</li>\n"
                note_html += "</ul>\n"
                # Append to both inline and attachment bodies so recipients see it regardless of attachment policy
                body = (body or '') + note_html
                # If we already built html_body_to_send, append there too; otherwise it will be built later
        except Exception:
            pass

        # Optionally attach full job log as a file instead of inlining it
        attach_path = None
        temp_files = []  # track temp files we create so we can cleanup reliably
        try:
            # Decide whether to attach the log based on settings and job outcome
            should_attach_log = attach_log_setting or (attach_on_failure_setting and failed_count > 0)
            should_attach = should_attach_log

            if should_attach:
                # Fetch job log from DB (best-effort)
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT log FROM jobs WHERE id = %s;", (job_id,))
                    row = cur.fetchone()
                    job_log = row.get('log') if row else ''

                if job_log:
                    import tempfile, os, time
                    from app.utils import filename_safe, filename_timestamp
                    temp_dir = tempfile.gettempdir()
                    # Include safe archive name and UTC timestamp in filename
                    if archive_name:
                        safe_archive = filename_safe(archive_name)[:40]
                        filename_core = f'job_{job_id}_{safe_archive}_{filename_timestamp()}'
                    else:
                        filename_core = f'job_{job_id}_{filename_timestamp()}'
                    attach_path = os.path.join(temp_dir, f"{filename_core}.log")
                    # Avoid overwriting an existing file with the same name (fallback to epoch suffix)
                    if os.path.exists(attach_path):
                        attach_path = os.path.join(temp_dir, f'{filename_core}_{int(time.time())}.log')
                    try:
                        with open(attach_path, 'w', encoding='utf-8') as f:
                            f.write(job_log)
                        temp_files.append(attach_path)
                    except Exception:
                        attach_path = None
        except Exception as e:
            logger.exception("Failed to prepare log attachment: %s", e)

        # Send email
        send_email(title, html_body_to_send, attach=attach_path, context=f'email_smtp_{archive_name}_{job_id}')
    except Exception as e:
        logger.exception("Failed to send notification: %s", e)


# Other handlers can be added here as needed