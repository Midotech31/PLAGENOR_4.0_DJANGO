import logging

from django.core.exceptions import ObjectDoesNotExist

from .models import Notification


logger = logging.getLogger(__name__)


def _safe_assigned_user(request_obj):
    """Return assigned analyst's user or None — defensive against orphaned FKs."""
    if not request_obj.assigned_to:
        return None
    try:
        return request_obj.assigned_to.user
    except ObjectDoesNotExist:
        return None
    except Exception:
        logger.exception(
            "Unable to resolve assigned analyst for request=%s",
            getattr(request_obj, 'pk', None),
        )
        return None


def notify_user(user, message, notification_type='INFO', request_obj=None,
               link_url='', link_text='', action_url='', action_text=''):
    """Create an in-app notification for a user with deep linking support."""
    # Auto-generate link URL if request_obj is provided
    if not link_url and request_obj:
        link_url = f"/dashboard/ops/request/{request_obj.pk}/"
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
    """Send notifications based on workflow events with deep linking.

    Entries are built lazily inside the matching branch so an unrelated
    transition can't crash on a partially-populated ``assigned_to`` row.
    """
    pk = request_obj.pk
    link_url = f"/dashboard/ops/request/{pk}/"
    link_text = f"Demande {request_obj.display_id}"

    def make(message, type_, targets, action_text='', action_url=''):
        return {
            'message': message,
            'type': type_,
            'targets': [t for t in targets if t is not None],
            'action_text': action_text,
            'action_url': action_url,
        }

    if to_status == 'VALIDATED':
        entry = make('Votre demande a été validée', 'STATUS_CHANGE',
                     [request_obj.requester], action_text='Voir les détails')
    elif to_status == 'REJECTED':
        entry = make('Votre demande a été rejetée', 'STATUS_CHANGE',
                     [request_obj.requester], action_text='Voir les détails')
    elif to_status == 'ASSIGNED':
        entry = make('Une analyse vous a été assignée', 'ASSIGNMENT',
                     [_safe_assigned_user(request_obj)],
                     action_text='Accepter la tâche',
                     action_url=f'/dashboard/ops/request/{pk}/accept/')
    elif to_status == 'REPORT_VALIDATED':
        entry = make('Le rapport a été validé', 'REPORT',
                     [request_obj.requester], action_text='Télécharger le rapport')
    elif to_status == 'COMPLETED':
        entry = make('Votre demande est complétée', 'STATUS_CHANGE',
                     [request_obj.requester], action_text='Voir le rapport')
    elif to_status == 'APPOINTMENT_PROPOSED':
        entry = make('Un rendez-vous a été proposé', 'APPOINTMENT',
                     [request_obj.requester], action_text='Confirmer le RDV',
                     action_url=f'/dashboard/ops/request/{pk}/confirm-appointment/')
    elif to_status == 'QUOTE_SENT':
        entry = make('Un devis a été préparé pour votre demande', 'PAYMENT',
                     [request_obj.requester], action_text='Voir le devis')
    elif to_status == 'PAYMENT_CONFIRMED':
        entry = make('Votre paiement a été confirmé', 'PAYMENT',
                     [request_obj.requester], action_text='Voir les détails')
    else:
        return

    for target in entry['targets']:
        if target and target != actor:
            notify_user(
                target,
                f"{entry['message']} — {request_obj.display_id}",
                entry['type'],
                request_obj,
                link_url=link_url,
                link_text=link_text,
                action_url=entry['action_url'],
                action_text=entry['action_text'],
            )


def notify_assignment(request_obj, analyst, assigned_by=None):
    """Send assignment notification with deep linking."""
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
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
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
    link_text = f"Demande {request_obj.display_id}"
    
    # Notify the requester
    if request_obj.requester and request_obj.requester != user:
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
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
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
    link_url = f"/dashboard/ops/request/{request_obj.pk}/"
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
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
    link_url = f"/dashboard/client/request/{request_obj.pk}/"
    link_text = f"Demande {request_obj.display_id}"
    
    if request_obj.requester:
        # Calculate the amount to pay
        amount = request_obj.admin_validated_price or request_obj.quote_amount or 0
        
        notify_user(
            request_obj.requester,
            f"Votre analyse pour {request_obj.display_id} est terminée. Paiement de {amount:,.0f} DZD requis pour recevoir le rapport.",
            'PAYMENT',
            request_obj,
            link_url=link_url,
            link_text=link_text,
            action_text='Effectuer le paiement',
        )
