# notifications/emails.py — PLAGENOR 4.0 Email Notification System

import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger('plagenor.email')


def send_email_notification(to_email, subject, body_html):
    """Send an HTML email notification."""
    try:
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email] if isinstance(to_email, str) else to_email,
            html_message=body_html,
            fail_silently=True,
        )
        logger.info("Email sent to %s: %s", to_email, subject)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)


def notify_submission_confirmation(request_obj):
    """Send confirmation after request submission."""
    if request_obj.requester and request_obj.requester.email:
        to_email = request_obj.requester.email
    elif request_obj.guest_email:
        to_email = request_obj.guest_email
    else:
        return

    body = render_to_string('notifications/email/submission_confirmation.html', {
        'request_obj': request_obj,
    })
    send_email_notification(
        to_email,
        f"[PLAGENOR] Demande {request_obj.display_id} — Confirmation de soumission",
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

    body = render_to_string('notifications/email/request_status_change.html', {
        'request_obj': request_obj,
        'old_status': old_status,
        'new_status': new_status,
    })
    send_email_notification(
        to_email,
        f"[PLAGENOR] Demande {request_obj.display_id} — Mise à jour de statut",
        body,
    )


def notify_assignment(request_obj, member_profile):
    """Notify analyst of a new assignment."""
    to_email = member_profile.user.email
    if not to_email:
        return

    body = render_to_string('notifications/email/assignment_notification.html', {
        'request_obj': request_obj,
        'member': member_profile,
    })
    send_email_notification(
        to_email,
        f"[PLAGENOR] Nouvelle assignation — {request_obj.display_id}",
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

    body = render_to_string('notifications/email/appointment_notification.html', {
        'request_obj': request_obj,
    })
    send_email_notification(
        to_email,
        f"[PLAGENOR] Rendez-vous programmé — {request_obj.display_id}",
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

    body = render_to_string('notifications/email/report_delivery.html', {
        'request_obj': request_obj,
    })
    send_email_notification(
        to_email,
        f"[PLAGENOR] Rapport disponible — {request_obj.display_id}",
        body,
    )


def notify_guest_tracking_code(request_obj):
    """Send tracking code to guest."""
    if not request_obj.guest_email:
        return

    body = render_to_string('notifications/email/guest_tracking_code.html', {
        'request_obj': request_obj,
    })
    send_email_notification(
        request_obj.guest_email,
        f"[PLAGENOR] Votre code de suivi — {request_obj.display_id}",
        body,
    )
