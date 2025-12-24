"""Notification-specific formatting helpers.

Includes HTML->text conversion, compact text builder and section splitting
logic used when crafting messages for chat services (Discord, etc.).
"""
from typing import List, Tuple
import re
from app.utils import format_bytes, get_disk_usage, get_archives_path


def strip_html_tags(html_text: str) -> str:
    """Convert HTML to plain text by removing tags and converting entities.

    Also removes <style> and <script> blocks to avoid leaving CSS/JS content behind.
    """
    if not html_text:
        return ''
    # Remove style/script blocks entirely
    text = re.sub(r'<(script|style)[\s\S]*?>[\s\S]*?<\/\1>', '', html_text, flags=re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Convert common HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    # Normalize whitespace and clean up multiple newlines
    text = re.sub(r'\r\n?', '\n', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def split_section_by_length(text: str, max_len: int) -> List[str]:
    """Split a long text into parts respecting paragraph boundaries where possible."""
    if not text:
        return ['']
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    paras = text.split('\n\n')
    cur: List[str] = []
    cur_len = 0
    for p in paras:
        p_with_sep = (p + '\n\n') if p else '\n\n'
        if cur_len + len(p_with_sep) <= max_len:
            cur.append(p_with_sep)
            cur_len += len(p_with_sep)
        else:
            if cur:
                parts.append(''.join(cur).rstrip())
            # If single paragraph too large, split by fixed chunk
            if len(p) > max_len:
                for i in range(0, len(p), max_len):
                    parts.append(p[i:i+max_len])
                cur = []
                cur_len = 0
            else:
                cur = [p_with_sep]
                cur_len = len(p_with_sep)
    if cur:
        parts.append(''.join(cur).rstrip())
    return parts


def build_compact_text(archive_name: str, stack_metrics: List[dict], created_archives: List[dict], total_size: int, size_str: str, duration_str: str, stacks_with_volumes: List[dict], reclaimed, base_url: str) -> Tuple[str, List[str]]:
    lines: List[str] = []
    lines.append(f"{archive_name} completed")
    lines.append(f"Stacks: {sum(1 for m in stack_metrics if m.get('status') == 'success')}/{len(stack_metrics)} successful  |  Total size: {size_str}  |  Duration: {duration_str}")
    lines.append("")

    if created_archives:
        lines.append("SUMMARY OF CREATED ARCHIVES")
        lines.append("")
        for a in created_archives:
            lines.append(f"{format_bytes(a['size'])} {a['path']}")
        lines.append("")
        lines.append(f"Total: {format_bytes(total_size)}")
        lines.append("")

    try:
        disk = get_disk_usage()
        if disk and disk['total']:
            lines.append("DISK USAGE (on /archives)")
            lines.append("")
            lines.append(f"Total: {format_bytes(disk['total'])}   Used: {format_bytes(disk['used'])} ({disk['percent']:.0f}% used)")
            try:
                total_archives_size = 0
                for root, dirs, files in __import__('os').walk(get_archives_path()):
                    for fn in files:
                        fp = __import__('os').path.join(root, fn)
                        try:
                            total_archives_size += __import__('os').path.getsize(fp)
                        except Exception:
                            continue
                lines.append(f"Backup Content Size (/archives): {format_bytes(total_archives_size)}")
            except Exception:
                pass
            lines.append("")
    except Exception:
        pass

    # Retention
    if reclaimed is None:
        lines.append("RETENTION SUMMARY")
        lines.append("")
        lines.append("No retention information available.")
        lines.append("")
    elif reclaimed == 0:
        lines.append("RETENTION SUMMARY")
        lines.append("")
        lines.append("No archives older than configured retention were deleted.")
        lines.append("")
    else:
        lines.append("RETENTION SUMMARY")
        lines.append("")
        lines.append(f"Freed space: {format_bytes(reclaimed)}")
        lines.append("")

    if stack_metrics:
        lines.append("STACKS PROCESSED")
        lines.append("")
        for metric in stack_metrics:
            ok = '✓' if metric.get('status') == 'success' else '✗'
            st_size = format_bytes(metric.get('archive_size_bytes') or 0)
            archive_p = metric.get('archive_path') or 'N/A'
            lines.append(f"{metric['stack_name']} {ok} {st_size} {archive_p}")
        lines.append("")

    if stacks_with_volumes:
        lines.append("⚠️ Named Volumes Warning")
        lines.append("Named volumes are NOT included in the backup archives. Consider backing them up separately.")
        lines.append("")
        for metric in stacks_with_volumes:
            volumes = metric.get('named_volumes') or []
            lines.append(f"{metric['stack_name']}: {', '.join(volumes)}")
        lines.append("")

    lines.append(f"View details: {base_url}/history?job=")

    compact_text = "\n".join(lines)

    # Truncate to safe size for chat services (Discord message limit ~2000 chars)
    if len(compact_text) > 1800:
        compact_text = compact_text[:1800] + "\n\n[Message truncated; full log attached]"

    return compact_text, lines
