from django.shortcuts import redirect


# Role → request-detail URL name. After a per-request action we send the
# user back to the request they acted on (so they see the updated state),
# rather than bouncing them to the dashboard index ("page principale").
_DETAIL_URL_BY_ROLE = {
    'REQUESTER': 'dashboard:requester_request_detail',
    'CLIENT': 'dashboard:client_request_detail',
    'MEMBER': 'dashboard:analyst_request_detail',
    'PLATFORM_ADMIN': 'dashboard:admin_request_detail',
    'SUPER_ADMIN': 'dashboard:admin_request_detail',
}


def safe_int(value, default=0):
    """Parse an int from untrusted input, falling back to `default`."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    """Parse a float from untrusted input, falling back to `default`."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def redirect_back(request, fallback_url='dashboard:router'):
    """Redirect to the referring page, preserving tab context."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    try:
        return redirect(fallback_url)
    except Exception:
        return redirect('/')


def redirect_to_detail(request, req, fallback_url='dashboard:router'):
    """Redirect to the request's role-specific detail page after an action.

    Keeps the user in context — they land on the request they just acted
    on (with its refreshed status/history) instead of being thrown back to
    the dashboard index. Falls back to ``redirect_back`` when the role has
    no detail page (e.g. FINANCE) or no request is available.
    """
    role = getattr(request.user, 'role', '')
    name = _DETAIL_URL_BY_ROLE.get(role)
    if name and req is not None and getattr(req, 'pk', None):
        try:
            return redirect(name, pk=req.pk)
        except Exception:
            pass
    return redirect_back(request, fallback_url)
