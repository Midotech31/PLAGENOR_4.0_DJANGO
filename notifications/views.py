from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from .models import Notification


@login_required
def notification_click(request, pk):
    """Mark notification as read and redirect to the relevant request detail page."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)

    # Mark as read
    if not notif.read:
        notif.read = True
        notif.save(update_fields=['read'])

    # Priority 1: Use explicit link_url if available (deep linking)
    if notif.link_url:
        return redirect(notif.link_url)

    # Priority 2: Redirect to the appropriate detail page based on user role
    if notif.request_id:
        url = _get_detail_url(request.user, notif.request)
        if url:
            return redirect(url)

    # Priority 3: Use action_url if available
    if notif.action_url:
        return redirect(notif.action_url)

    # Fallback: redirect to dashboard
    return redirect('dashboard:router')


def _get_detail_url(user, req):
    """Return the correct request detail URL based on user role."""
    from django.urls import reverse

    role = user.role

    if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
        return reverse('dashboard:admin_request_detail', args=[req.pk])
    elif role == 'MEMBER':
        # Only if user is the assigned analyst
        try:
            if req.assigned_to and req.assigned_to.user_id == user.pk:
                return reverse('dashboard:analyst_request_detail', args=[req.pk])
        except Exception as e:
            logger.warning(f"Failed to get analyst request detail URL for request {req.pk}: {e}")
        return None
    elif role == 'REQUESTER':
        if req.requester_id == user.pk:
            return reverse('dashboard:requester_request_detail', args=[req.pk])
        return None
    elif role == 'CLIENT':
        if req.requester_id == user.pk:
            return reverse('dashboard:client_request_detail', args=[req.pk])
        return None
    elif role == 'FINANCE':
        return reverse('dashboard:finance')
    return None


@login_required
def mark_all_read(request):
    """Mark all notifications as read for the current user."""
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, read=False).update(read=True)
    return redirect('dashboard:router')
