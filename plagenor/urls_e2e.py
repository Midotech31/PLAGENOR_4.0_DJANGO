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
