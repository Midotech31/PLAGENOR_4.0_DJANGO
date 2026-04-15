from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Request
from messaging.models import EphemeralMessage, Reminder
from messaging.permissions import can_send_message, can_view_messages
from messaging.services import (
    archive_phase_messages, deactivate_reminders,
    _notify_message_participants, _send_reminder_notification,
    _notify_escalation, create_reminder
)


@login_required
def request_messages(request, pk):
    """GET: Return messages for current phase. POST: Send a new message."""
    request_obj = get_object_or_404(Request, pk=pk)

    if request.method == 'GET':
        if not can_view_messages(request.user, request_obj):
            return JsonResponse({'error': 'No access'}, status=403)

        messages = EphemeralMessage.objects.filter(
            request=request_obj,
            is_archived=False
        ).select_related('sender').order_by('created_at')

        can_send, reason = can_send_message(request.user, request_obj)

        return JsonResponse({
            'messages': [
                {
                    'id': str(m.id),
                    'sender_name': m.sender.get_full_name() if m.sender else 'System',
                    'sender_role': _get_sender_role(m.sender, request_obj),
                    'content': m.content,
                    'created_at': m.created_at.isoformat(),
                    'is_system': m.is_system_message,
                    'is_mine': m.sender == request.user,
                    'attachment_url': m.attachment.url if m.attachment else None,
                    'attachment_name': m.attachment_name,
                }
                for m in messages
            ],
            'can_send': can_send,
            'current_phase': request_obj.status,
            'phase_label': request_obj.get_status_display(),
        })

    elif request.method == 'POST':
        can_send, reason = can_send_message(request.user, request_obj)
        if not can_send:
            return JsonResponse({'error': 'Cannot send messages'}, status=403)

        content = request.POST.get('content', '').strip()
        attachment = request.FILES.get('attachment')
        attachment_name = ''

        if not content and not attachment:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
        if len(content) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        if attachment:
            if attachment.size > 5 * 1024 * 1024:
                return JsonResponse({'error': 'Attachment too large (max 5MB)'}, status=400)
            attachment_name = attachment.name

        msg = EphemeralMessage.objects.create(
            request=request_obj,
            phase=request_obj.status,
            sender=request.user,
            content=content,
            attachment=attachment,
            attachment_name=attachment_name,
        )

        _notify_message_participants(request_obj, request.user, content)

        return JsonResponse({
            'status': 'sent',
            'message': {
                'id': str(msg.id),
                'sender_name': request.user.get_full_name(),
                'content': msg.content,
                'created_at': msg.created_at.isoformat(),
                'is_mine': True,
            }
        })


@login_required
def request_message_history(request, pk):
    """GET: Return archived messages grouped by phase."""
    request_obj = get_object_or_404(Request, pk=pk)
    if not can_view_messages(request.user, request_obj):
        return JsonResponse({'error': 'No access'}, status=403)

    archived = EphemeralMessage.objects.filter(
        request=request_obj,
        is_archived=True
    ).select_related('sender').order_by('created_at')

    phases = {}
    for msg in archived:
        phase_display = msg.get_status_display() if msg.phase else msg.phase
        if msg.phase not in phases:
            phases[msg.phase] = {
                'label': phase_display,
                'messages': []
            }
        phases[msg.phase]['messages'].append({
            'sender_name': msg.sender.get_full_name() if msg.sender else 'System',
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
            'is_system': msg.is_system_message,
        })

    return JsonResponse({'phases': phases})


@login_required
def my_reminders(request):
    """Get reminders for current user."""
    reminders = Reminder.objects.filter(
        target_user=request.user,
        is_active=True
    ).select_related('request', 'request__service').order_by('-created_at')

    return JsonResponse({
        'reminders': [
            {
                'id': str(r.id),
                'request_id': str(r.request.id),
                'request_display_id': r.request.display_id,
                'service_name': r.request.service.name if r.request.service else '',
                'action_expected': r.action_expected,
                'urgency': r.urgency,
                'source': r.source,
                'created_at': r.created_at.isoformat(),
                'pending_hours': int((timezone.now() - r.created_at).total_seconds() / 3600),
            }
            for r in reminders
        ]
    })


@login_required
@require_POST
def acknowledge_reminder(request, pk):
    """Acknowledge/dismiss a reminder."""
    reminder = get_object_or_404(Reminder, pk=pk, target_user=request.user)
    reminder.acknowledged_at = timezone.now()
    reminder.save(update_fields=['acknowledged_at'])
    return JsonResponse({'status': 'acknowledged'})


def _get_sender_role(sender, request_obj):
    """Return human-readable role label for message display."""
    if not sender:
        return 'system'
    role = getattr(sender, 'role', None)
    if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
        return 'Admin'
    if hasattr(sender, 'member_profile') and request_obj.assigned_to == sender.member_profile:
        return 'Analyst'
    if request_obj.requester == sender:
        return 'Requester' if request_obj.channel == 'IBTIKAR' else 'Client'
    return 'User'
