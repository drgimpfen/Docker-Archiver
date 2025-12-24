"""Centralized helpers to send sectioned/embed Discord notifications.

This module provides a single entry point `send_to_discord` which handles
splitting long messages into sections, building simple HTML for each section
and calling a `DiscordAdapter` to deliver each part. It intentionally keeps
dependencies minimal so it can be unit tested with a fake adapter.
"""
from typing import List, Optional
import time
import copy
from app.utils import get_logger
from .formatters import split_section_by_length, build_section_html

logger = get_logger(__name__)


def send_to_discord(discord_adapter, title: str, body_html: str, compact_text: str, sections: List[str], attach_file: Optional[str] = None, embed_options: dict = None, max_desc: int = 4000, pause: float = 0.2, view_url: Optional[str] = None) -> dict:
    """Send a rich (HTML) message to Discord using the provided adapter.

    Behavior:
    - If the compact_text fits within `max_desc` a single message is sent with
      the provided full `body_html` so Apprise can render a single embed.
    - Otherwise the message is split into `sections` and each section is
      split via `split_section_by_length` and sent individually. The attachment
      (if provided) is included only on the final section's final part.
    - `embed_options` are applied to each send; the footer is removed on
      intermediate parts to avoid repetition.

    Returns a dictionary with keys:
    - sent_any: bool — whether at least one send returned success
    - details: optional message or list of errors
    """
    if discord_adapter is None:
        return {'sent_any': False, 'details': 'no adapter'}

    sent_any = False
    errors = []

    try:
        # Simple case: send full html once
        if compact_text and len(compact_text) <= max_desc:
            try:
                # Ensure we pass a string body to Apprise/Discord adapter
                b_html = body_html if isinstance(body_html, str) else str(body_html)
                # If there's an attachment, perform a two-step send: first embeds (no attach), then a short attach message
                if attach_file:
                    res_embed = discord_adapter.send(title, b_html, body_format=__import__('apprise').NotifyFormat.HTML, attach=None, context='discord_single', embed_options=embed_options)
                    # Prepare attach message content (plain text, include view_url if available)
                    try:
                        from app.notifications.formatters import strip_html_tags
                        attach_body = strip_html_tags(b_html)
                    except Exception:
                        attach_body = compact_text or ''
                    if view_url:
                        attach_body = f"{attach_body}\n\nView details: {view_url}"
                    # Truncate to Discord 2000 limit
                    if len(attach_body) > 2000:
                        attach_body = attach_body[:1950].rstrip() + '\n\n...(truncated, see attachment)'
                    res_attach = discord_adapter.send(title, attach_body, body_format=None, attach=attach_file, context='discord_attach')
                    # Evaluate
                    if res_embed.success and res_attach.success:
                        return {'sent_any': True}
                    details = []
                    if not res_embed.success:
                        details.append(f"embed: {res_embed.detail}")
                    if not res_attach.success:
                        details.append(f"attach: {res_attach.detail}")
                    return {'sent_any': res_embed.success or res_attach.success, 'details': details}
                else:
                    res = discord_adapter.send(title, b_html, body_format=__import__('apprise').NotifyFormat.HTML, attach=None, context='discord_single', embed_options=embed_options)
            except Exception as e:
                logger.exception("send_to_discord: exception during single send (title=%s): %s -- body_type=%s embed_type=%s", title, e, type(body_html), type(embed_options))
                return {'sent_any': False, 'details': str(e)}
            if res.success:
                return {'sent_any': True}
            # Log the offending parameter types for debugging
            logger.error("send_to_discord: single send failed - types: title=%s body_type=%s attach=%s embed_options_type=%s detail=%s", type(title), type(b_html), type(attach_file), type(embed_options), res.detail)
            return {'sent_any': False, 'details': res.detail}

        # Otherwise send sectioned messages
        last_section = sections[-1] if sections else None
        for sec in sections:
            parts = split_section_by_length(sec, max_desc)
            for idx, part in enumerate(parts):
                is_final = (sec == last_section and idx == len(parts) - 1)
                attach = attach_file if is_final else None

                # Per-part embed options: remove footer for intermediate parts
                sec_embed_opts = copy.deepcopy(embed_options or {})
                if not is_final and 'footer' in sec_embed_opts:
                    sec_embed_opts.pop('footer', None)

                sec_html = build_section_html(part)
                # Defensive: coerce to str to avoid passing a dict or other types to Apprise
                if not isinstance(sec_html, str):
                    logger.warning("send_to_discord: coerced non-str section html to str (type=%s)", type(sec_html))
                    sec_html = str(sec_html)
                # Limit title length—Discord embed title limitations
                sec_title = (part.split('\n', 1)[0] or title)[:250]

                try:
                    # Always send sections without the attach parameter. Attachment will be sent as a single follow-up message after sections.
                    res = discord_adapter.send(sec_title, sec_html, body_format=__import__('apprise').NotifyFormat.HTML, attach=None, context='discord_section', embed_options=sec_embed_opts)
                except Exception as e:
                    logger.exception("send_to_discord: exception during section send (title=%s): %s", sec_title, e)
                    errors.append(str(e))
                    continue

                if res.success:
                    sent_any = True
                else:
                    # Log parameter types for debugging
                    logger.error("send_to_discord: section send failed - types: title=%s body=%s attach=%s embed_options=%s detail=%s", type(sec_title), type(sec_html), type(attach), type(sec_embed_opts), res.detail)
                    errors.append(res.detail)

                # Small pause to reduce rate-limit risk
                if pause:
                    time.sleep(pause)

        # After sections: if an attachment is provided, send it as a single follow-up message
        if attach_file:
            try:
                # Use the stripped HTML as the attach message content if available
                try:
                    from app.notifications.formatters import strip_html_tags
                    attach_body = strip_html_tags(body_html)
                except Exception:
                    attach_body = compact_text or ''
                if view_url:
                    attach_body = f"{attach_body}\n\nView details: {view_url}"
                if len(attach_body) > 2000:
                    attach_body = attach_body[:1950].rstrip() + '\n\n...(truncated, see attachment)'

                res_attach = discord_adapter.send(title, attach_body, body_format=None, attach=attach_file, context='discord_attach')
                if res_attach.success:
                    sent_any = True
                else:
                    errors.append(res_attach.detail)
            except Exception as e:
                logger.exception("send_to_discord: exception during attach send: %s", e)
                errors.append(str(e))

        if sent_any:
            return {'sent_any': True}
        return {'sent_any': False, 'details': errors}

    except Exception as e:
        logger.exception("send_to_discord: unexpected error: %s", e)
        return {'sent_any': False, 'details': str(e)}
