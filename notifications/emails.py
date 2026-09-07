# notifications/emails.py — PLAGENOR 4.0 Email Notification System

import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from urllib.parse import urljoin
from notifications.models import Notification
from django.utils.translation import override

logger = logging.getLogger('plagenor.email')


def send_email_notification(to_email, subject, body_html):
    """Send an HTML email notification.

    We deliberately use `fail_silently=False` and rely on the surrounding
    try/except: that way SMTP failures are logged with a useful message
    instead of being silently swallowed twice.
    """
    try:
        sent = send_mail(
            subject=subject,
            message=strip_tags(body_html),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email] if isinstance(to_email, str) else to_email,
            html_message=body_html,
            fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("SMTP backend did not accept the message")
        logger.info("Email notification accepted by backend: %s", subject)
        return True
    except Exception as e:
        logger.error("Failed to send email notification %s: %s", subject, e)
        return False


def _email_ctx(request_obj, **extra):
    """Shared template context for every notification email.

    The HTML templates reference ``{{ request.* }}`` everywhere, but
    rendering happens OUTSIDE an HTTP request (so there's no real
    HttpRequest in scope). We pass ``request_obj`` under BOTH names so the
    templates render whether they reach for ``request`` or ``request_obj``
    — a long-standing variable-name mismatch that was silently producing
    blank emails (Django's invalid-variable lookup returns '' in normal
    render mode, so the failure was invisible until something tripped it).
    """
    ctx = {
        'request': request_obj,        # what the templates actually use
        'request_obj': request_obj,    # legacy callers + safety
        'language': getattr(getattr(request_obj, 'requester', None),
                             'preferred_language', 'fr') or 'fr',
        'base_url': settings.PUBLIC_BASE_URL,
        'dashboard_url': urljoin(settings.PUBLIC_BASE_URL, Notification(
            user=request_obj.requester, request=request_obj).get_absolute_url())
            if request_obj.requester else urljoin(settings.PUBLIC_BASE_URL, f'/track/?q={request_obj.guest_token}'),
        'support_email': 'genomicsplatform.essbo@gmail.com',
        'user_name': (request_obj.requester.get_full_name()
                       if request_obj.requester else
                       (request_obj.guest_name or '')),
    }
    member = extra.get('member')
    if member:
        ctx['language'] = getattr(member.user, 'preferred_language', 'fr') or 'fr'
        ctx['user_name'] = member.user.get_full_name() or member.user.username
        ctx['dashboard_url'] = urljoin(settings.PUBLIC_BASE_URL, Notification(user=member.user, request=request_obj).get_absolute_url())
    for key, value in extra.items():
        ctx[key] = urljoin(settings.PUBLIC_BASE_URL, value) if key.endswith('_url') and value else value
    return ctx


def notify_submission_confirmation(request_obj):
    """Send confirmation after request submission."""
    if request_obj.requester and request_obj.requester.email:
        to_email = request_obj.requester.email
    elif request_obj.guest_email:
        to_email = request_obj.guest_email
    else:
        return

    body = _render_email('notifications/email/submission_confirmation.html',
                            _email_ctx(request_obj))
    send_email_notification(
        to_email,
        _subject(request_obj.display_id, _email_ctx(request_obj)['language'], 'Confirmation de soumission', 'Submission received', 'تأكيد استلام الطلب'),
        body,
    )


def notify_status_change(request_obj, old_status, new_status):
    """Notify requester of a status change."""
    if request_obj.requester and request_obj.requester.email:
        to_email = request_obj.requester.email
    elif request_obj.guest_email:
        to_email = request_obj.guest_email
    else:
        return

    new_status_display = dict(request_obj.STATUS_CHOICES).get(new_status, new_status)
    body = _render_email('notifications/email/request_status_change.html',
                            _email_ctx(request_obj,
                                       old_status=old_status,
                                       new_status=new_status,
                                       new_status_display=new_status_display))
    send_email_notification(
        to_email,
        _subject(request_obj.display_id, _email_ctx(request_obj)['language'], 'Mise à jour de statut', 'Status update', 'تحديث حالة الطلب'),
        body,
    )


def notify_assignment(request_obj, member_profile):
    """Notify analyst of a new assignment."""
    to_email = member_profile.user.email
    if not to_email:
        return

    body = _render_email('notifications/email/assignment_notification.html',
                            _email_ctx(request_obj, member=member_profile))
    send_email_notification(
        to_email,
        _subject(request_obj.display_id, getattr(member_profile.user, 'preferred_language', 'fr'), 'Nouvelle assignation', 'New assignment', 'تكليف جديد'),
        body,
    )


def notify_appointment(request_obj):
    """Notify about appointment scheduling."""
    if request_obj.requester and request_obj.requester.email:
        to_email = request_obj.requester.email
    elif request_obj.guest_email:
        to_email = request_obj.guest_email
    else:
        return

    body = _render_email('notifications/email/appointment_notification.html',
                            _email_ctx(request_obj,
                                       appointment_date=getattr(request_obj, 'appointment_date', None),
                                       appointment_time=getattr(request_obj, 'appointment_time', ''),
                                       appointment_note=getattr(request_obj, 'appointment_note', '')))
    send_email_notification(
        to_email,
        _subject(request_obj.display_id, _email_ctx(request_obj)['language'], 'Rendez-vous programmé', 'Appointment scheduled', 'تم تحديد الموعد'),
        body,
    )


def notify_report_delivery(request_obj):
    """Notify that report is available, with clickable link."""
    if request_obj.requester and request_obj.requester.email:
        to_email = request_obj.requester.email
    elif request_obj.guest_email:
        to_email = request_obj.guest_email
    else:
        return

    token = getattr(request_obj, 'report_token', None)
    body = _render_email('notifications/email/report_delivery.html',
                            _email_ctx(request_obj,
                                       report_url=f'/report/{token}/' if token else ''))
    send_email_notification(
        to_email,
        _subject(request_obj.display_id, _email_ctx(request_obj)['language'], 'Rapport disponible', 'Report available', 'التقرير متاح'),
        body,
    )


def notify_guest_tracking_code(request_obj):
    """Send tracking code to guest."""
    if not request_obj.guest_email:
        return

    body = _render_email('notifications/email/guest_tracking_code.html',
                            _email_ctx(request_obj,
                                       guest_name=request_obj.guest_name or '',
                                       tracking_url=f'/track/?q={request_obj.guest_token}',
                                       register_url='/accounts/register/'))
    send_email_notification(
        request_obj.guest_email,
        _subject(request_obj.display_id, _email_ctx(request_obj)['language'], 'Votre code de suivi', 'Your tracking code', 'رمز تتبع طلبك'),
        body,
    )


def _render_email(template, context):
    with override(context.get('language', 'fr')):
        return render_to_string(template, context)


def _subject(reference, language, fr, en, ar):
    return f"[PLAGENOR] {reference} — {dict(fr=fr, en=en, ar=ar).get(language, fr)}"
