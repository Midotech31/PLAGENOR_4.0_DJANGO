from dashboard.utils import redirect_back
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages as django_messages

from core.models import Request, Message


@login_required
def send_message(request, pk):
    """Send a message within a request context."""
    if request.method != 'POST':
        return HttpResponseForbidden()

    req = get_object_or_404(Request, pk=pk)
    text = request.POST.get('message_text', '').strip()
    if not text:
        django_messages.error(request, "Le message ne peut pas être vide.")
        return _redirect_by_role(request.user)

    user = request.user

    if user.is_admin:
        # Admin sends to assigned member
        if req.assigned_to:
            to_user = req.assigned_to.user
        else:
            django_messages.error(request, "Aucun analyste assigné.")
            return _redirect_by_role(user)
        Message.objects.create(request=req, from_user=user, to_user=to_user, text=text, step=req.status)

    elif user.role == 'MEMBER':
        # Member message is visible to BOTH the platform admin AND the requester.
        # Find the last-acting admin for the primary message.
        from accounts.models import User as UserModel
        last_admin = req.history.filter(
            actor__role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN']
        ).order_by('-created_at').values_list('actor', flat=True).first()
        admin_user = UserModel.objects.filter(pk=last_admin).first() if last_admin else None

        # Always create a copy visible to the requester
        requester = req.requester
        recipients = set()
        if admin_user:
            recipients.add(admin_user)
        if requester and requester != admin_user:
            recipients.add(requester)

        if not recipients:
            django_messages.error(request, "Impossible de déterminer le destinataire.")
            return _redirect_by_role(user)

        for recipient in recipients:
            Message.objects.create(request=req, from_user=user, to_user=recipient, text=text, step=req.status)

    else:
        django_messages.error(request, "Action non autorisée.")
        return _redirect_by_role(user)

    django_messages.success(request, "Message envoyé.")
    return _redirect_by_role(user)


def _redirect_by_role(user):
    role_routes = {
        'SUPER_ADMIN': 'dashboard:superadmin',
        'PLATFORM_ADMIN': 'dashboard:admin_ops',
        'MEMBER': 'dashboard:analyst',
        'FINANCE': 'dashboard:finance',
        'REQUESTER': 'dashboard:requester',
        'CLIENT': 'dashboard:client',
    }
    return redirect(role_routes.get(user.role, 'dashboard:admin_ops'))
