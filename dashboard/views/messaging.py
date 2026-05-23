from dashboard.utils import redirect_back
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages as django_messages

from core.models import Request, Message


@login_required
def send_message(request, pk):
    """Send a message within a request thread.

    Authorization (P2-H5): only one of
      * an admin (SUPER_ADMIN / PLATFORM_ADMIN),
      * the analyst (MEMBER) currently assigned to this request, or
      * the request's own requester (CLIENT or REQUESTER)
    may post into a thread. Unrelated analysts can no longer inject messages
    into requests they have nothing to do with.
    """
    if request.method != 'POST':
        return HttpResponseForbidden()

    req = get_object_or_404(Request, pk=pk)
    text = request.POST.get('message_text', '').strip()
    if not text:
        django_messages.error(request, "Le message ne peut pas être vide.")
        return _redirect_by_role(request.user)

    user = request.user

    # ── Authorization gate ──────────────────────────────────────────────
    is_admin = user.is_admin
    is_assigned_member = (
        user.role == 'MEMBER'
        and req.assigned_to_id is not None
        and req.assigned_to.user_id == user.pk
    )
    is_owner = user.role in ('CLIENT', 'REQUESTER') and req.requester_id == user.pk
    if not (is_admin or is_assigned_member or is_owner):
        return HttpResponseForbidden()

    # ── Recipient resolution ────────────────────────────────────────────
    from accounts.models import User as UserModel

    if is_admin:
        # Admins primarily message the assigned analyst; if none assigned
        # yet, fall back to the requester.
        if req.assigned_to_id and req.assigned_to.user_id:
            recipients = {req.assigned_to.user}
        elif req.requester_id:
            recipients = {req.requester}
        else:
            django_messages.error(request, "Aucun destinataire disponible.")
            return _redirect_by_role(user)

    elif is_assigned_member:
        # Member message visible to both the admin and the requester.
        last_admin_pk = req.history.filter(
            actor__role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN']
        ).order_by('-created_at').values_list('actor', flat=True).first()
        admin_user = (
            UserModel.objects.filter(pk=last_admin_pk).first()
            if last_admin_pk else None
        )
        recipients = set()
        if admin_user:
            recipients.add(admin_user)
        if req.requester_id and req.requester != admin_user:
            recipients.add(req.requester)
        if not recipients:
            # Fallback to any active admin so the message isn't lost.
            recipients = set(UserModel.objects.filter(
                role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True,
            )[:1])

    else:  # is_owner — CLIENT or REQUESTER
        # The request owner messages the analyst (if assigned) plus admins.
        recipients = set()
        if req.assigned_to_id and req.assigned_to.user_id:
            recipients.add(req.assigned_to.user)
        # Always copy admins so the conversation is supervised.
        admin_users = UserModel.objects.filter(
            role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True,
        )
        for admin in admin_users:
            recipients.add(admin)
        if not recipients:
            django_messages.error(request, "Aucun destinataire disponible.")
            return _redirect_by_role(user)

    for recipient in recipients:
        if recipient and recipient != user:
            Message.objects.create(
                request=req, from_user=user, to_user=recipient,
                text=text, step=req.status,
            )

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
