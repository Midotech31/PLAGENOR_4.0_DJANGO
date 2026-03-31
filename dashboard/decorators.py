"""
Standardized permission decorators for dashboard views.
All decorators follow the same pattern for consistency.
"""
from functools import wraps
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required


def role_required(role):
    """
    Factory decorator that creates role-based permission decorators.
    
    Usage:
        @role_required('ADMIN')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden("Authentication required.")
            if request.user.role != role:
                return HttpResponseForbidden(f"Role '{role}' required.")
            return view_func(request, *args, **kwargs)
        wrapper.__wrapped__ = view_func
        return login_required(wrapper)
    return decorator


def superadmin_required(view_func):
    """Require SUPER_ADMIN role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role != 'SUPER_ADMIN':
            return HttpResponseForbidden("Super admin access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def admin_required(view_func):
    """Require SUPER_ADMIN or PLATFORM_ADMIN role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return HttpResponseForbidden("Admin access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def analyst_required(view_func):
    """Require MEMBER role (analyst)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role != 'MEMBER':
            return HttpResponseForbidden("Analyst access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def requester_required(view_func):
    """Require REQUESTER role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role != 'REQUESTER':
            return HttpResponseForbidden("Requester access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def client_required(view_func):
    """Require CLIENT role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role != 'CLIENT':
            return HttpResponseForbidden("Client access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def finance_required(view_func):
    """Require FINANCE role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role != 'FINANCE':
            return HttpResponseForbidden("Finance access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def staff_required(view_func):
    """Require any staff role (SUPER_ADMIN, PLATFORM_ADMIN, MEMBER, FINANCE)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Authentication required.")
        if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER', 'FINANCE'):
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)
