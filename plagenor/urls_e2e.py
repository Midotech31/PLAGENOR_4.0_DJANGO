"""Loopback-only session bootstrap for the isolated Playwright environment."""

from django.contrib.auth import login
from django.http import Http404, HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from accounts.models import User
from plagenor.urls import urlpatterns as production_urlpatterns


E2E_USERNAMES = frozenset({
    'admin', 'admin_ops', 'analyst', 'finance', 'amina', 'client',
})


@csrf_exempt
def create_e2e_session(request, username):
    """Authenticate a seeded fixture without storing browser credentials.

    This URLconf is loaded only by ``settings_e2e``. CSRF is unnecessary for
    this test-only bootstrap because the socket-peer check accepts loopback
    traffic exclusively; forwarded headers are deliberately ignored here.
    """
    if request.method != 'POST' or request.META.get('REMOTE_ADDR') not in {
            '127.0.0.1', '::1'} or username not in E2E_USERNAMES:
        raise Http404
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist as exc:
        raise Http404 from exc
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return HttpResponse(status=204)


urlpatterns = [
    path('__e2e__/session/<str:username>/', create_e2e_session),
] + production_urlpatterns


@csrf_exempt
def create_financial_fixture(request):
    """Isolated browser fixture; this route never exists in production."""
    from uuid import uuid4
    from django.http import JsonResponse
    from core.models import Request, Service
    if (request.method != 'POST' or request.META.get('REMOTE_ADDR') not in {'127.0.0.1', '::1'}
            or not request.user.is_authenticated or request.user.username != 'admin_ops'):
        raise Http404
    service, _ = Service.objects.get_or_create(code='E2E-FINANCE', defaults={'name': 'Prestation de test', 'genoclab_price': 1000})
    req = Request.objects.create(display_id='E2E-'+uuid4().hex[:12], title='Recette financière OHB',
        channel='GENOCLAB', status='REQUEST_CREATED', service=service, requester=User.objects.get(username='client'))
    return JsonResponse({'id': str(req.pk)})


urlpatterns.insert(0, path('__e2e__/financial-request/', create_financial_fixture))
