from .models import Notification


def _get_request_link_url(request_obj, user=None):
    """Get the correct link URL based on request channel and user role.
    
    Returns role-appropriate URL for viewing the request.
    """
    if user and hasattr(user, 'role'):
        role = user.role
        if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return f"/dashboard/ops/request/{request_obj.pk}/"
        elif role == 'MEMBER':
            return f"/dashboard/analyst/request/{request_obj.pk}/"
        elif role == 'FINANCE':
            return f"/dashboard/ops/request/{request_obj.pk}/"
    
    if request_obj.channel == 'GENOCLAB':
        return f"/dashboard/client/request/{request_obj.pk}/"
    elif request_obj.channel == 'IBTIKAR':
        return f"/dashboard/requester/request/{request_obj.pk}/"
    return f"/dashboard/ops/request/{request_obj.pk}/"


def _get_client_link_url(request_obj):
    """Legacy function for backward compatibility. Use _get_request_link_url instead."""
    return _get_request_link_url(request_obj)


def notify_user(user, message, notification_type='INFO', request_obj=None,
               link_url='', link_text='', action_url='', action_text=''):
    """Create an in-app notification for a user with deep linking support."""
    if not link_url and request_obj:
        link_url = _get_request_link_url(request_obj, user)
        if not link_text:
            link_text = f"Voir la demande {request_obj.display_id}"
    
    Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        request=request_obj,
        link_url=link_url,
        link_text=link_text,
        action_url=action_url,
        action_text=action_text,
    )


def notify_workflow_transition(request_obj, to_status, actor):
    """Send notifications based on workflow events with deep linking."""
    notifications = {
        'VALIDATED': {
            'message': 'Votre demande a été validée',
            'type': 'STATUS_CHANGE',
            'targets': [request_obj.requester],
            'action_text': 'Voir les détails',
        },
        'REJECTED': {
            'message': 'Votre demande a été rejetée',
            'type': 'STATUS_CHANGE',
            'targets': [request_obj.requester],
            'action_text': 'Voir les détails',
        },
        'ASSIGNED': {
            'message': 'Une analyse vous a été assignée',
            'type': 'ASSIGNMENT',
            'targets': [request_obj.assigned_to.user if request_obj.assigned_to else None],
            'action_text': 'Accepter la tâche',
            'action_url': f'/dashboard/ops/request/{request_obj.pk}/accept/',
        },
        'REPORT_VALIDATED': {
            'message': 'Le rapport a été validé',
            'type': 'REPORT',
            'targets': [request_obj.requester],
            'action_text': 'Télécharger le rapport',
        },
        'COMPLETED': {
            'message': 'Votre demande est complétée',
            'type': 'STATUS_CHANGE',
            'targets': [request_obj.requester],
            'action_text': 'Voir le rapport',
        },
        'APPOINTMENT_PROPOSED': {
            'message': 'Un rendez-vous a été proposé',
            'type': 'APPOINTMENT',
            'targets': [request_obj.requester],
            'action_text': 'Confirmer le RDV',
            'action_url': f'/dashboard/ops/request/{request_obj.pk}/confirm-appointment/',
        },
        'QUOTE_SENT': {
            'message': 'Un devis a été préparé pour votre demande',
            'type': 'PAYMENT',
            'targets': [request_obj.requester],
            'action_text': 'Voir le devis',
        },
        'PAYMENT_CONFIRMED': {
            'message': 'Votre paiement a été confirmé',
            'type': 'PAYMENT',
            'targets': [request_obj.requester],
            'action_text': 'Voir les détails',
        },
    }

    entry = notifications.get(to_status)
    if entry:
        msg = entry['message']
        notif_type = entry['type']
        targets = entry['targets']
        action_text = entry.get('action_text', '')
        action_url = entry.get('action_url', '')
        link_text = f"Demande {request_obj.display_id}"
        
        for target in targets:
            if target and target != actor:
                link_url = _get_request_link_url(request_obj, target)
                notify_user(
                    target,
                    f"{msg} — {request_obj.display_id}",
                    notif_type,
                    request_obj,
                    link_url=link_url,
                    link_text=link_text,
                    action_url=action_url,
                    action_text=action_text,
                )


def notify_assignment(request_obj, analyst, assigned_by=None):
    """Send assignment notification with deep linking."""
    link_url = _get_request_link_url(request_obj, analyst)
    link_text = f"Voir la demande {request_obj.display_id}"
    action_url = f"/dashboard/ops/request/{request_obj.pk}/accept/"
    
    notify_user(
        analyst,
        f"Une nouvelle analyse vous a été assignée: {request_obj.display_id}",
        'ASSIGNMENT',
        request_obj,
        link_url=link_url,
        link_text=link_text,
        action_url=action_url,
        action_text='Accepter la tâche',
    )


def notify_status_change(request_obj, old_status, new_status, user=None):
    """Send status change notification with deep linking."""
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester and request_obj.requester != user:
        link_url = _get_request_link_url(request_obj, request_obj.requester)
        notify_user(
            request_obj.requester,
            f"Statut de votre demande {request_obj.display_id} changé: {old_status} → {new_status}",
            'STATUS_CHANGE',
            request_obj,
            link_url=link_url,
            link_text=link_text,
        )


def notify_report_ready(request_obj):
    """Send notification when report is ready with deep linking."""
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
        link_url = _get_request_link_url(request_obj, request_obj.requester)
        notify_user(
            request_obj.requester,
            f"Le rapport pour votre demande {request_obj.display_id} est prêt",
            'REPORT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Télécharger le rapport',
        )


def notify_payment_required(request_obj, amount):
    """Send payment required notification."""
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
        link_url = _get_request_link_url(request_obj, request_obj.requester)
        notify_user(
            request_obj.requester,
            f"Un paiement de {amount:,.0f} DZD est requis pour {request_obj.display_id}",
            'PAYMENT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Effectuer le paiement',
        )


def get_unread_count(user):
    """Return the number of unread notifications for a user."""
    return Notification.objects.filter(user=user, read=False).count()


def get_recent_notifications(user, limit=10):
    """Return recent notifications for a user."""
    return Notification.objects.filter(user=user).select_related('request')[:limit]


def mark_all_as_read(user):
    """Mark all notifications as read for a user."""
    from django.utils import timezone
    Notification.objects.filter(user=user, read=False).update(
        read=True,
        read_at=timezone.now()
    )


def notify_purchase_order_uploaded(request_obj):
    """Notify admin that client has uploaded purchase order (Bon de commande).
    
    Per Algerian commercial code, purchase order is mandatory for commercial transactions.
    """
    from accounts.models import User
    
    # Get all admins and platform admins
    admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
    
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
    link_text = f"Voir la demande {request_obj.display_id}"
    
    for admin in admins:
        notify_user(
            admin,
            f"Nouveau Bon de Commande téléchargé pour {request_obj.display_id}",
            'STATUS_CHANGE',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Vérifier le Bon de Commande',
        )


def notify_payment_received(request_obj):
    """Notify assigned analyst that payment has been received and they can now upload the report.
    
    This is the final step before report delivery - payment gate ensures clients pay
    before receiving their analysis reports.
    """
    link_url = f"/dashboard/analyst/request/{request_obj.pk}/"
    link_text = f"Voir la demande {request_obj.display_id}"
    
    # Notify the assigned analyst
    if request_obj.assigned_to and request_obj.assigned_to.user:
        notify_user(
            request_obj.assigned_to.user,
            f"Paiement confirmé pour {request_obj.display_id} — Vous pouvez maintenant télécharger le rapport d'analyse",
            'REPORT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Télécharger le rapport',
        )
    
    # Also notify admins
    from accounts.models import User
    admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
    
    for admin in admins:
        notify_user(
            admin,
            f"Paiement confirmé pour {request_obj.display_id} — En attente de téléchargement du rapport",
            'PAYMENT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
        )


def notify_payment_request(request_obj):
    """Notify client that they need to pay to receive their report.
    
    This is triggered when analysis is finished - client must pay before
    receiving the analysis report.
    """
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
        amount = request_obj.admin_validated_price or request_obj.quote_amount or 0
        link_url = _get_request_link_url(request_obj, request_obj.requester)
        
        notify_user(
            request_obj.requester,
            f"Votre analyse pour {request_obj.display_id} est terminée. Paiement de {amount:,.0f} DZD requis pour recevoir le rapport.",
            'PAYMENT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Effectuer le paiement',
        )


def notify_admin_task_declined(request_obj, declined_by, reason=''):
    """Notify admins that a member has declined an assigned task.
    
    This allows the admin to reassign the task to another member.
    """
    from accounts.models import User
    
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
    link_text = f"Demande {request_obj.display_id}"
    
    reason_text = f" | Raison: {reason}" if reason else ""
    
    admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
    
    for admin in admins:
        notify_user(
            admin,
            f"Tâche {request_obj.display_id} déclinée par {declined_by.user.get_full_name()}{reason_text}",
            'WORKFLOW',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Réassigner',
        )


def notify_sample_received(request_obj):
    """Notify user that sample has been received with tracking invitation.
    
    Bilingual FR/EN message confirming sample receipt and inviting to track progress.
    """
    if not request_obj.requester:
        return
    
    if request_obj.channel == 'GENOCLAB':
        tracking_number = request_obj.tracking_number or request_obj.display_id
    else:
        tracking_number = request_obj.ibtikar_id or request_obj.display_id
    
    message_fr = (
        f"✓ Échantillon reçu pour {request_obj.display_id} ! "
        f"N° suivi: {tracking_number}. "
        f"Consultez votre profil ou suivez en ligne."
    )
    message_en = (
        f"✓ Sample received for {request_obj.display_id}! "
        f"Tracking: {tracking_number}. "
        f"Check your profile or track online."
    )
    
    link_url = _get_request_link_url(request_obj, request_obj.requester)
    
    notify_user(
        request_obj.requester,
        f"{message_fr} | {message_en}",
        'STATUS_CHANGE',
        request_obj,
        link_url=link_url,
        link_text="Voir ma demande / View my request",
        action_url="/track/",
        action_text="Suivre en ligne / Track online",
    )
