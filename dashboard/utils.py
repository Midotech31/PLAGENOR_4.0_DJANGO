from django.shortcuts import redirect
from django.urls import NoReverseMatch


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


def confirm_appointment_flow(request, req):
    """Confirme le rendez-vous proposé, de façon idempotente et robuste.

    Gère tous les cas qui faisaient échouer la confirmation côté demandeur /
    client :
      * statut déjà à APPOINTMENT_CONFIRMED (ou plus avancé) mais drapeau
        ``appointment_confirmed`` resté à False → on synchronise le drapeau ;
      * date posée mais statut resté à ASSIGNED → on régularise vers
        APPOINTMENT_PROPOSED avant de confirmer ;
      * cas normal APPOINTMENT_PROPOSED → confirmation.
    Pose les messages utilisateur ; ne redirige pas (le caller s'en charge).
    """
    import uuid
    from django.contrib import messages
    from django.utils import timezone
    from core.workflow import transition
    from core.exceptions import InvalidTransitionError, AuthorizationError

    # Statuts où le RDV est déjà acté au niveau du workflow.
    _CONFIRMED_OR_LATER = {
        'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED', 'ANALYSIS_STARTED',
        'ANALYSIS_FINISHED', 'REPORT_UPLOADED', 'ADMIN_REVIEW',
        'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'COMPLETED', 'CLOSED',
    }

    def _sync_flag():
        updated = []
        if not req.appointment_confirmed:
            req.appointment_confirmed = True
            req.appointment_confirmed_at = timezone.now()
            updated += ['appointment_confirmed', 'appointment_confirmed_at']
        if not req.report_token:
            req.report_token = uuid.uuid4()
            updated.append('report_token')
        if updated:
            req.save(update_fields=updated)

    if req.status in _CONFIRMED_OR_LATER:
        _sync_flag()
        messages.success(request, f"Rendez-vous confirmé pour {req.display_id}.")
        return

    if req.status == 'ASSIGNED' and req.appointment_date:
        try:
            transition(req, 'APPOINTMENT_PROPOSED',
                       req.appointment_proposed_by or request.user,
                       notes='RDV proposé (régularisation)', force=True)
        except (InvalidTransitionError, AuthorizationError, ValueError):
            pass

    if req.status != 'APPOINTMENT_PROPOSED':
        messages.error(
            request,
            "Aucun rendez-vous à confirmer pour le moment. "
            "L'analyste doit d'abord proposer une date."
        )
        return

    try:
        transition(req, 'APPOINTMENT_CONFIRMED', request.user, notes='RDV confirmé')
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
        return

    _sync_flag()
    messages.success(request, f"Rendez-vous confirmé pour {req.display_id}.")


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
        except NoReverseMatch:
            pass
    return redirect_back(request, fallback_url)
