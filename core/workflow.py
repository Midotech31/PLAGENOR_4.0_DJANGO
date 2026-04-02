# core/workflow.py — PLAGENOR 4.0 Workflow Engine (Django)
# Integrates state_machine.py transitions with role-based permission checks.

import logging

from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.utils import timezone

from core.models import Request, RequestHistory

logger = logging.getLogger('plagenor.workflow')
from core.state_machine import (
    IBTIKAR_TRANSITIONS,
    GENOCLAB_TRANSITIONS,
    get_allowed_next_states,
    validate_transition,
    is_terminal,
)
from core.exceptions import InvalidTransitionError, AuthorizationError
from core.audit import log_workflow_transition

# Role-based permissions: which roles can trigger which transitions
# Format: {(from_status, to_status): [allowed_roles]}
ROLE_PERMISSIONS = {
    # IBTIKAR validations
    ('SUBMITTED', 'VALIDATION_PEDAGOGIQUE'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SUBMITTED', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_PEDAGOGIQUE', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_FINANCE', 'PLATFORM_NOTE_GENERATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('VALIDATION_FINANCE', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER'],
    ('IBTIKAR_CODE_SUBMITTED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # Analyst workflow — appointment states
    ('ASSIGNED', 'APPOINTMENT_PROPOSED'): ['SUPER_ADMIN', 'MEMBER'],
    ('APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER', 'CLIENT'],
    ('APPOINTMENT_PROPOSED', 'APPOINTMENT_RESCHEDULING_REQUESTED'): ['CLIENT'],
    ('APPOINTMENT_RESCHEDULING_REQUESTED', 'APPOINTMENT_PROPOSED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER'],
    ('APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER'],
    ('SAMPLE_RECEIVED', 'ANALYSIS_STARTED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_STARTED', 'ANALYSIS_FINISHED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_FINISHED', 'REPORT_UPLOADED'): ['SUPER_ADMIN', 'MEMBER'],
    # GENOCLAB: Allow report upload after payment confirmation
    ('PAYMENT_CONFIRMED', 'REPORT_UPLOADED'): ['SUPER_ADMIN', 'MEMBER'],
    ('REPORT_UPLOADED', 'REPORT_VALIDATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REPORT_UPLOADED', 'ANALYSIS_STARTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],  # Revision loop
    ('REPORT_VALIDATED', 'SENT_TO_REQUESTER'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SENT_TO_REQUESTER', 'COMPLETED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER'],
    ('COMPLETED', 'CLOSED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # GENOCLAB validations
    ('REQUEST_CREATED', 'QUOTE_DRAFT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REQUEST_CREATED', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'QUOTE_SENT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_SENT', 'QUOTE_VALIDATED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_SENT', 'QUOTE_REJECTED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_VALIDATED_BY_CLIENT', 'ORDER_UPLOADED'): ['CLIENT'],
    ('ORDER_UPLOADED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('PAYMENT_PENDING', 'PAYMENT_UPLOADED'): ['CLIENT'],
    ('PAYMENT_UPLOADED', 'PAYMENT_CONFIRMED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('REPORT_VALIDATED', 'SENT_TO_CLIENT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SENT_TO_CLIENT', 'COMPLETED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'CLIENT'],
    ('COMPLETED', 'ARCHIVED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
}


def get_allowed_transitions(request_obj):
    """Return list of allowed next statuses for a request."""
    return list(get_allowed_next_states(request_obj.channel, request_obj.status))


def check_role_permission(request_obj, to_status, actor) -> bool:
    """Check if actor's role allows this transition. SUPER_ADMIN always allowed."""
    if getattr(actor, 'role', '') == 'SUPER_ADMIN':
        return True
    key = (request_obj.status, to_status)
    allowed_roles = ROLE_PERMISSIONS.get(key)
    if allowed_roles is None:
        # No explicit rule — allow by default (permissive for unlisted transitions)
        return True
    return getattr(actor, 'role', '') in allowed_roles


def transition(request_obj, to_status, actor, notes='', force=False):
    """
    Transition a request to a new status, recording history.
    Validates the transition against the state machine and role permissions.
    Raises InvalidTransitionError or AuthorizationError on failure.
    """
    old_status = request_obj.status

    if not force:
        # Validate state machine
        allowed = get_allowed_next_states(request_obj.channel, old_status)
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Transition {old_status} -> {to_status} non autorisée pour le canal {request_obj.channel}. "
                f"États autorisés: {sorted(allowed) if allowed else 'AUCUN (état terminal)'}"
            )

        # Validate role permissions
        if not check_role_permission(request_obj, to_status, actor):
            raise AuthorizationError(
                f"Le rôle {getattr(actor, 'role', '?')} n'est pas autorisé pour la transition "
                f"{old_status} -> {to_status}"
            )

    request_obj.status = to_status
    request_obj.save(update_fields=['status', 'updated_at'])

    RequestHistory.objects.create(
        request=request_obj,
        from_status=old_status,
        to_status=to_status,
        actor=actor,
        notes=notes,
        forced=force,
    )

    # Audit log
    log_workflow_transition(request_obj, old_status, to_status, actor, {'notes': notes, 'forced': force})

    # Email notifications for key transitions
    _send_transition_emails(request_obj, old_status, to_status)

    # In-app notifications for key transitions
    _create_notifications(request_obj, to_status)

    # Auto-generate documents on specific transitions
    _auto_generate_documents(request_obj, to_status)

    return request_obj


def _create_notifications(request_obj, to_status):
    """Create in-app notifications for ALL workflow transitions."""
    try:
        from notifications.models import Notification
        from accounts.models import User
        from notifications.services import notify_sample_received

        # Sample received notification with tracking invitation
        if to_status == 'SAMPLE_RECEIVED':
            notify_sample_received(request_obj)

        # Notify the assigned member on relevant transitions
        if request_obj.assigned_to and to_status in (
            'ASSIGNED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
            # GENOCLAB: Member should be notified of all relevant steps
            'PAYMENT_CONFIRMED',  # Member can now upload report
            'REPORT_VALIDATED',  # Admin validated the report
            'SENT_TO_CLIENT',    # Report sent to client
        ):
            Notification.objects.create(
                user=request_obj.assigned_to.user,
                message=f"{request_obj.display_id}: {request_obj.get_status_display()}",
                request=request_obj,
                notification_type='WORKFLOW',
            )

        # Notify the requester/client on relevant transitions
        if request_obj.requester and to_status in (
            # IBTIKAR states
            'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE', 'PLATFORM_NOTE_GENERATED',
            'IBTIKAR_SUBMISSION_PENDING', 'ASSIGNED', 'APPOINTMENT_PROPOSED',
            'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'COMPLETED', 'REJECTED',
            # GENOCLAB states - Full pipeline notifications
            'QUOTE_SENT', 'INVOICE_GENERATED', 'PAYMENT_CONFIRMED',
            'SENT_TO_CLIENT',
            'ORDER_UPLOADED',  # Client uploads purchase order
            'PAYMENT_PENDING',  # Client needs to pay
            'REPORT_UPLOADED',  # Report uploaded, awaiting validation
            'REPORT_VALIDATED',  # Report validated
        ):
            Notification.objects.create(
                user=request_obj.requester,
                message=f"{request_obj.display_id}: {request_obj.get_status_display()}",
                request=request_obj,
                notification_type='WORKFLOW',
            )

        # Always notify admins for important transitions
        if to_status in (
            'SUBMITTED', 'IBTIKAR_CODE_SUBMITTED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'REPORT_UPLOADED', 'REQUEST_CREATED',
            # GENOCLAB admin-relevant states
            'QUOTE_VALIDATED_BY_CLIENT', 'QUOTE_REJECTED_BY_CLIENT', 'PAYMENT_CONFIRMED',
            'APPOINTMENT_RESCHEDULING_REQUESTED',  # Client requested rescheduling
            'PAYMENT_UPLOADED',  # Client uploaded payment receipt
        ):
            admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    message=f"Nouvelle action: {request_obj.display_id} → {request_obj.get_status_display()}",
                    request=request_obj,
                    notification_type='WORKFLOW',
                )
    except Exception as e:
        # Log notification errors but don't break the workflow transition
        logger.exception(
            f"Failed to create notifications for request {request_obj.display_id}: {str(e)}",
            extra={
                'request_id': str(request_obj.id),
                'request_display_id': request_obj.display_id,
                'to_status': to_status,
            }
        )


def _send_transition_emails(request_obj, old_status, to_status):
    """Send email notifications for key workflow transitions.
    
    Implements bilingual (FR/EN) email notifications using Django's email backend
    configured in settings.py. Each notification type uses appropriate templates
    and includes proper error handling with logging.
    """
    try:
        # Check if email is configured
        if not getattr(settings, 'EMAIL_HOST', None) or settings.EMAIL_HOST in ('', 'localhost'):
            logger.debug(f"Email not configured, skipping notification for request {request_obj.display_id}")
            return
        
        _notify_requester_on_transition(request_obj, old_status, to_status)
        _notify_analyst_on_transition(request_obj, old_status, to_status)
        _notify_admins_on_transition(request_obj, old_status, to_status)
        
    except Exception as e:
        logger.error(
            f"Failed to send transition emails for request {request_obj.display_id}: {str(e)}",
            extra={
                'request_id': str(request_obj.id),
                'request_display_id': request_obj.display_id,
                'old_status': old_status,
                'to_status': to_status,
            },
            exc_info=True
        )


def _get_user_language(user):
    """Get user's preferred language, defaulting to French."""
    if hasattr(user, 'language'):
        return user.language
    return 'fr'


def _render_bilingual_email(template_name, context, subject_fr, subject_en):
    """Render email content in both French and English."""
    from django.template.loader import render_to_string
    
    base_url = getattr(settings, 'BASE_URL', 'https://plagenor.essbo.dz')
    support_email = getattr(settings, 'SUPPORT_EMAIL', 'contact@plagenor.essbo.dz')
    
    # Add common context
    context['base_url'] = base_url
    context['support_email'] = support_email
    context['dashboard_url'] = f"{base_url}/dashboard/"
    context['request'] = context.get('request_obj', context.get('request'))
    
    # Render French version
    context['language'] = 'fr'
    html_fr = render_to_string(template_name, context)
    
    # Render English version
    context['language'] = 'en'
    html_en = render_to_string(template_name, context)
    
    return html_fr, html_en


def _send_email(to_email, subject, html_content, recipient_name=''):
    """Send HTML email with proper error handling."""
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings
    
    try:
        # Create plain text version by stripping HTML
        import re
        text_content = re.sub(r'<[^>]+>', '', html_content)
        text_content = re.sub(r'\n+', '\n', text_content).strip()
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email] if isinstance(to_email, str) else to_email,
        )
        email.attach_alternative(html_content, 'text/html')
        email.send(fail_silently=False)
        
        logger.info(
            f"Email sent successfully to {to_email}: {subject}",
            extra={'recipient': to_email, 'subject': subject}
        )
        return True
        
    except Exception as e:
        logger.error(
            f"Failed to send email to {to_email}: {str(e)}",
            extra={'recipient': to_email, 'subject': subject},
            exc_info=True
        )
        return False


def _notify_requester_on_transition(request_obj, old_status, to_status):
    """Send email to requester/client on relevant status changes."""
    from django.conf import settings
    
    # Determine recipient
    if request_obj.requester and request_obj.requester.email:
        recipient = request_obj.requester
        recipient_email = recipient.email
        recipient_name = recipient.get_full_name() or recipient.username
    elif request_obj.guest_email:
        recipient_email = request_obj.guest_email
        recipient_name = request_obj.guest_name or 'Guest'
        recipient = None
    else:
        return  # No email available
    
    # Statuses that warrant email to requester
    notification_statuses = {
        'VALIDATION_PEDAGOGIQUE': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Validation pédagogique",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Pedagogical Validation",
            'next_steps_fr': [
                "Votre demande est en cours de validation pédagogique",
                "Vous recevrez une notification une fois la validation terminée"
            ],
            'next_steps_en': [
                "Your request is being validated pedagogically",
                "You will receive a notification once validation is complete"
            ]
        },
        'VALIDATION_FINANCE': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Validation financière",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Financial Validation",
            'next_steps_fr': [
                "Votre demande est en cours de validation financière IBTIKAR",
                "Veuillez attendre la confirmation de votre budget"
            ],
            'next_steps_en': [
                "Your request is being validated financially",
                "Please wait for budget confirmation"
            ]
        },
        'ASSIGNED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Analyste assigné",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Analyst Assigned",
            'next_steps_fr': [
                "Un analyste a été assigné à votre demande",
                "Vous recevrez les détails du rendez-vous bientôt"
            ],
            'next_steps_en': [
                "An analyst has been assigned to your request",
                "You will receive appointment details soon"
            ]
        },
        'APPOINTMENT_PROPOSED': {
            'template': 'notifications/email/appointment_notification.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Proposition de rendez-vous",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Appointment Proposed",
            'is_appointment': True,
        },
        'APPOINTMENT_CONFIRMED': {
            'template': 'notifications/email/appointment_notification.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Rendez-vous confirmé",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Appointment Confirmed",
            'is_appointment': True,
        },
        'QUOTE_SENT': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Devis prêt",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Quote Ready",
            'next_steps_fr': [
                "Votre devis est prêt et en attente de votre validation",
                "Veuillez vous connecter pour accepter ou refuser le devis"
            ],
            'next_steps_en': [
                "Your quote is ready and awaiting your validation",
                "Please log in to accept or reject the quote"
            ]
        },
        'PAYMENT_CONFIRMED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Paiement confirmé",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Payment Confirmed",
            'next_steps_fr': [
                "Votre paiement a été confirmé",
                "L'analyse de vos échantillons va commencer"
            ],
            'next_steps_en': [
                "Your payment has been confirmed",
                "Analysis of your samples will begin"
            ]
        },
        'REPORT_UPLOADED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Rapport uploadé",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Report Uploaded",
            'next_steps_fr': [
                "Votre rapport d'analyse a été uploadé",
                "Il est en cours de validation par l'administrateur"
            ],
            'next_steps_en': [
                "Your analysis report has been uploaded",
                "It is being validated by the administrator"
            ]
        },
        'REPORT_VALIDATED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Rapport validé",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Report Validated",
            'next_steps_fr': [
                "Votre rapport a été validé",
                "Vous recevrez une notification lorsqu'il sera prêt"
            ],
            'next_steps_en': [
                "Your report has been validated",
                "You will receive a notification when it's ready"
            ]
        },
        'SENT_TO_REQUESTER': {
            'template': 'notifications/email/report_delivery.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Rapport disponible",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Report Available",
            'is_report': True,
        },
        'SENT_TO_CLIENT': {
            'template': 'notifications/email/report_delivery.html',
            'subject_fr': f"[PLAGENOR] Facture {request_obj.display_id} — Rapport disponible",
            'subject_en': f"[PLAGENOR] Invoice {request_obj.display_id} — Report Available",
            'is_report': True,
        },
        'COMPLETED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Complétée",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Completed",
            'next_steps_fr': [
                "Votre demande est maintenant complétée",
                "Merci d'évaluer notre service"
            ],
            'next_steps_en': [
                "Your request is now complete",
                "Thank you for rating our service"
            ]
        },
        'REJECTED': {
            'template': 'notifications/email/request_status_change.html',
            'subject_fr': f"[PLAGENOR] Demande {request_obj.display_id} — Demande rejetée",
            'subject_en': f"[PLAGENOR] Request {request_obj.display_id} — Request Rejected",
            'next_steps_fr': [
                "Malheureusement, votre demande a été rejetée",
                "Veuillez contacter le support pour plus d'informations"
            ],
            'next_steps_en': [
                "Unfortunately, your request has been rejected",
                "Please contact support for more information"
            ]
        },
    }
    
    if to_status not in notification_statuses:
        return
    
    config = notification_statuses[to_status]
    template = config['template']
    
    # Build context
    context = {
        'request_obj': request_obj,
        'user_name': recipient_name,
        'new_status_display': request_obj.get_status_display(),
        'status_message': None,
    }
    
    if 'next_steps_fr' in config:
        lang = _get_user_language(recipient) if recipient else 'fr'
        context['next_steps'] = config['next_steps_fr'] if lang == 'fr' else config['next_steps_en']
    
    if config.get('is_appointment'):
        context['appointment_date'] = request_obj.appointment_date
        context['appointment_time'] = getattr(request_obj, 'appointment_time', None)
        context['appointment_note'] = getattr(request_obj, 'appointment_note', None)
        if request_obj.assigned_to:
            context['analyst_name'] = request_obj.assigned_to.user.get_full_name()
    
    if config.get('is_report'):
        base_url = getattr(settings, 'BASE_URL', 'https://plagenor.essbo.dz')
        context['report_url'] = f"{base_url}/reports/{request_obj.report_token}/"
    
    # Render and send email
    html_fr, html_en = _render_bilingual_email(
        template, context,
        config['subject_fr'], config['subject_en']
    )
    
    # Determine subject based on user language
    lang = _get_user_language(recipient) if recipient else 'fr'
    subject = config['subject_fr'] if lang == 'fr' else config['subject_en']
    html_content = html_fr if lang == 'fr' else html_en
    
    _send_email(recipient_email, subject, html_content, recipient_name)


def _notify_analyst_on_transition(request_obj, old_status, to_status):
    """Send email to assigned analyst on relevant status changes."""
    if not request_obj.assigned_to:
        return
    
    analyst = request_obj.assigned_to.user
    if not analyst.email:
        return
    
    analyst_name = analyst.get_full_name() or analyst.username
    notification_statuses = ['ASSIGNED', 'PAYMENT_CONFIRMED']
    
    if to_status not in notification_statuses:
        return
    
    if to_status == 'ASSIGNED':
        template = 'notifications/email/assignment_notification.html'
        subject_fr = f"[PLAGENOR] Nouvelle assignation — {request_obj.display_id}"
        subject_en = f"[PLAGENOR] New Assignment — {request_obj.display_id}"
        
        base_url = getattr(settings, 'BASE_URL', 'https://plagenor.essbo.dz')
        context = {
            'request': request_obj,
            'member': request_obj.assigned_to,
            'dashboard_url': f"{base_url}/dashboard/analyst/",
        }
        
        html_fr, html_en = _render_bilingual_email(template, context, subject_fr, subject_en)
        
        lang = _get_user_language(analyst)
        subject = subject_fr if lang == 'fr' else subject_en
        html_content = html_fr if lang == 'fr' else html_en
        
        _send_email(analyst.email, subject, html_content, analyst_name)


def _notify_admins_on_transition(request_obj, old_status, to_status):
    """Send email to admins on important status changes."""
    from accounts.models import User
    from django.conf import settings
    
    # Only notify admins for critical transitions
    critical_statuses = ['SUBMITTED', 'IBTIKAR_CODE_SUBMITTED', 'REPORT_UPLOADED']
    
    if to_status not in critical_statuses:
        return
    
    admins = User.objects.filter(
        role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'],
        is_active=True
    ).exclude(email='')
    
    base_url = getattr(settings, 'BASE_URL', 'https://plagenor.essbo.dz')
    subject_fr = f"[PLAGENOR] Action requise — {request_obj.display_id}"
    subject_en = f"[PLAGENOR] Action Required — {request_obj.display_id}"
    
    context = {
        'request': request_obj,
        'user_name': 'Admin',
        'new_status_display': request_obj.get_status_display(),
        'dashboard_url': f"{base_url}/dashboard/admin/",
        'next_steps_fr': ["Veuillez examiner cette demande depuis le tableau de bord admin"],
        'next_steps_en': ["Please review this request from the admin dashboard"],
    }
    
    html_fr, html_en = _render_bilingual_email(
        'notifications/email/request_status_change.html',
        context, subject_fr, subject_en
    )
    
    for admin in admins:
        lang = _get_user_language(admin)
        subject = subject_fr if lang == 'fr' else subject_en
        html_content = html_fr if lang == 'fr' else html_en
        _send_email(admin.email, subject, html_content, admin.get_full_name())


def _auto_generate_documents(request_obj, to_status):
    """Auto-generate PDF documents on specific workflow transitions.
    
    PDF Generation Triggers:
    - IBTIKAR Form: On request submission (SUBMITTED) or IBTIKAR submission (IBTIKAR_SUBMISSION_PENDING)
    - Platform Note: On validation (PLATFORM_NOTE_GENERATED) - IBTIKAR only
    - Reception Form: On appointment confirmation (APPOINTMENT_CONFIRMED) or sample receipt (SAMPLE_RECEIVED)
    """
    try:
        if request_obj.channel == 'IBTIKAR':
            # Generate IBTIKAR Form PDF on submission
            if to_status in ('SUBMITTED', 'IBTIKAR_SUBMISSION_PENDING', 'VALIDATION_PEDAGOGIQUE'):
                logger.info(f"Auto-generating IBTIKAR form PDF for request {request_obj.display_id}")
                try:
                    from documents.pdf_generator_ibtikar import generate_ibtikar_form_pdf
                    file_path, error = generate_ibtikar_form_pdf(request_obj, force_regenerate=False)
                    if error:
                        logger.warning(f"IBTIKAR form generation warning for {request_obj.display_id}: {error}")
                    else:
                        logger.info(f"IBTIKAR form PDF generated successfully: {file_path}")
                except Exception as e:
                    logger.error(f"Error generating IBTIKAR form PDF: {e}", exc_info=True)
            
            # Generate Platform Note PDF on validation (after financial validation)
            if to_status == 'PLATFORM_NOTE_GENERATED':
                logger.info(f"Auto-generating Platform Note PDF for request {request_obj.display_id}")
                try:
                    from documents.pdf_generator_platform_note import generate_platform_note_pdf
                    from notifications.services import notify_user
                    
                    file_path, error = generate_platform_note_pdf(request_obj, force_regenerate=True)
                    if error:
                        logger.warning(f"Platform Note PDF generation warning for {request_obj.display_id}: {error}")
                    else:
                        logger.info(f"Platform Note PDF generated successfully: {file_path}")
                        
                        # Send notification to requester
                        if request_obj.requester:
                            lang = getattr(request_obj.requester, 'language', 'fr') or 'fr'
                            message = (
                                f"Votre Note de Plateforme pour la demande {request_obj.display_id} "
                                f"est maintenant disponible au téléchargement. / "
                                f"Your Platform Note for request {request_obj.display_id} "
                                f"is now available for download."
                            )
                            notify_user(
                                user=request_obj.requester,
                                message=message,
                                notification_type='DOCUMENT_READY',
                                request_obj=request_obj,
                            )
                except Exception as e:
                    logger.error(f"Error generating Platform Note PDF: {e}", exc_info=True)
        
        # Generate Reception Form PDF on appointment confirmation or sample receipt
        if to_status in ('APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED'):
            logger.info(f"Auto-generating Reception Form PDF for request {request_obj.display_id}")
            try:
                from documents.pdf_generator_reception import generate_reception_form_pdf
                file_path, error = generate_reception_form_pdf(request_obj, force_regenerate=True)
                if error:
                    logger.warning(f"Reception Form PDF generation warning for {request_obj.display_id}: {error}")
                else:
                    logger.info(f"Reception Form PDF generated successfully: {file_path}")
            except Exception as e:
                logger.error(f"Error generating Reception Form PDF: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(
            f"Failed to auto-generate document for request {request_obj.display_id}: {str(e)}",
            extra={
                'request_id': str(request_obj.id),
                'request_display_id': request_obj.display_id,
                'to_status': to_status,
            },
            exc_info=True
        )
