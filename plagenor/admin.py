"""Keep Django's technical administration behind the application security gates."""
from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache


class SystemAdminSite(AdminSite):
    def has_permission(self, request):
        return super().has_permission(request) and request.user.role == 'SUPER_ADMIN'

    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        if request.user.is_authenticated:
            if self.has_permission(request):
                return redirect('admin:index')
            return HttpResponseForbidden()
        next_url = request.GET.get('next', '')
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = reverse('admin:index')
        # The application's login includes account lockout, IP throttling and
        # enrolled TOTP. Django's separate password form bypassed these gates.
        return redirect(reverse('accounts:login') + '?' + urlencode({'next': next_url}))
