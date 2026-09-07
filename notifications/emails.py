# notifications/emails.py — PLAGENOR 4.0 Email Notification System

import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.urls import reverse

logger = logging.getLogger('plagenor.email')


def send_email_notification(to_email, subject, body_html):
    """Send an HTML email notification.

    We deliberately use `fail_silently=False` and rely on the surrounding
    try/except: that way SMTP failures are logged with a useful message
    instead of being silently swallowed twice.
    """
    try:
        recipients = [to_email] if isinstance(to_email, str) else list(to_email or [])
        recipients = list(dict.fromkeys(address.strip() for address in recipients if address and address.strip()))
        if not recipients:
            return False
        accepted = send_mail(
            subject=subject,
            message=strip_tags(body_html),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=body_html,
            fail_silently=False,
        )
        if accepted != 1:
            logger.error('Email backend did not accept the notification.')
            return False
        logger.info("Email notification sent: %s", subject)
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
    base_url = settings.PUBLIC_BASE_URL.rstrip('/')
    recipient = extra.get('recipient') or (extra.get('member').user if extra.get('member') else request_obj.requester)
    role = getattr(recipient, 'role', '')
    routes = {'SUPER_ADMIN': 'dashboard:admin_request_detail', 'PLATFORM_ADMIN': 'dashboard:admin_request_detail',
              'MEMBER': 'dashboard:analyst_request_detail', 'CLIENT': 'dashboard:client_request_detail',
              'REQUESTER': 'dashboard:requester_request_detail'}
    path = reverse(routes[role], args=[request_obj.pk]) if role in routes else ('/dashboard/finance/' if role == 'FINANCE' else '/track/')
    ctx = {
        'request': request_obj,        # what the templates actually use
        'request_obj': request_obj,    # legacy callers + safety
        'language': getattr(recipient,
                             'preferred_language', 'fr') or 'fr',
        'base_url': base_url,
        'dashboard_url': base_url + path,
        'support_email': settings.DEFAULT_FROM_EMAIL,
        'user_name': (recipient.get_full_name() or recipient.username) if recipient else request_obj.guest_name,
    }
    ctx.update(extra)
    for key in ('report_url', 'tracking_url', 'register_url'):
        if ctx.get(key, '').startswith('/'):
            ctx[key] = base_url + ctx[key]
    return ctx


from django.utils.translation import gettext as _, gettext_noop, override

EVENT_TEXT = {
    'submission_confirmation': (
        gettext_noop('Confirmation de soumission'),
        gettext_noop('Votre demande a été reçue. Notre équipe vérifiera les informations et vous communiquera les prochaines étapes.')),
    'request_status_change': (
        gettext_noop('Mise à jour de votre demande'),
        gettext_noop('Le statut de votre demande a changé. Consultez votre espace pour connaître les actions attendues.')),
    'assignment_notification': (
        gettext_noop('Nouvelle demande assignée'),
        gettext_noop('Une demande vous a été assignée. Consultez les détails et organisez sa prise en charge depuis votre espace.')),
    'appointment_notification': (
        gettext_noop('Rendez-vous de votre demande'),
        gettext_noop('Les informations de rendez-vous ont été mises à jour. Consultez votre espace pour les vérifier ou les confirmer.')),
    'report_delivery': (
        gettext_noop('Rapport disponible'),
        gettext_noop('Votre rapport est disponible. Utilisez le lien sécurisé ci-dessous pour le consulter.')),
    'guest_tracking_code': (
        gettext_noop('Votre code de suivi'),
        gettext_noop('Conservez ce code confidentiel : il permet de consulter l’avancement de votre demande.')),
}


def _deliver(event, req, **extra):
    ctx = _email_ctx(req, **extra)
    recipient = extra.get('recipient') or (extra['member'].user if extra.get('member') else req.requester)
    to_email = getattr(recipient, 'email', '') or (req.guest_email if not recipient else '')
    if not to_email:
        return False
    language = ctx['language'] if ctx['language'] in ('fr', 'en', 'ar') else 'fr'
    with override(language):
        from core.models import PlatformContent
        custom = dict(PlatformContent.objects.filter(lang=language,
            key__in=[f'email_{event}_subject', f'email_{event}_body']).values_list('key','value'))
        title, content = EVENT_TEXT[event]
        ctx['subject'] = custom.get(f'email_{event}_subject') or _(title)
        ctx['intro'] = custom.get(f'email_{event}_body') or _(content)
        ctx['status_display'] = _(dict(req.STATUS_CHOICES).get(extra.get('new_status', req.status), req.status))
        ctx['event'] = event
        ctx['language'] = language
        ctx['primary_url'] = ctx.get('report_url') or ctx.get('tracking_url') or ctx['dashboard_url']
        body = render_to_string('notifications/email/event.html', ctx)
        return send_email_notification(to_email, f"[PLAGENOR] {req.display_id} — {ctx['subject']}", body)


def notify_submission_confirmation(request_obj):
    return _deliver('submission_confirmation', request_obj)


def notify_status_change(request_obj, old_status, new_status):
    return _deliver('request_status_change', request_obj, old_status=old_status, new_status=new_status)


def notify_assignment(request_obj, member_profile):
    return _deliver('assignment_notification', request_obj, member=member_profile)


def notify_appointment(request_obj):
    return _deliver('appointment_notification', request_obj)


def notify_report_delivery(request_obj):
    token = getattr(request_obj, 'report_token', None)
    return _deliver('report_delivery', request_obj, report_url=f'/report/{token}/' if token else '')


def notify_guest_tracking_code(request_obj):
    if request_obj.guest_email:
        return _deliver('guest_tracking_code', request_obj,
            tracking_url=f'/track/?q={request_obj.guest_token}', register_url='/accounts/register/')
