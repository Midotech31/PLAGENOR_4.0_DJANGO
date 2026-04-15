TERMINAL_STATES = {'CLOSED', 'ARCHIVED', 'ADMINISTRATIVELY_CLOSED'}


def can_send_message(user, request_obj):
    """
    Check if user can send messages on this request.
    Returns (bool, reason_string)
    """
    if request_obj.status in TERMINAL_STATES:
        return False, "closed"

    role = getattr(user, 'role', None)

    if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
        return True, "admin"

    if hasattr(user, 'member_profile'):
        if request_obj.assigned_to == user.member_profile:
            return True, "assigned_member"

        if request_obj.informed_members.filter(pk=user.member_profile.pk).exists():
            return False, "observer_read_only"

    if request_obj.requester == user:
        return True, "requester"

    return False, "no_access"


def can_view_messages(user, request_obj):
    """
    Check if user can view messages on this request.
    Observers CAN view but not send.
    """
    can_send, reason = can_send_message(user, request_obj)
    if can_send:
        return True
    if reason == "observer_read_only":
        return True
    if reason == "requester":
        return True
    return False
