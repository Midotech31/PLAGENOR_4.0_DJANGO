"""
Standardized permission decorators for dashboard views.
All decorators follow the same pattern for consistency.
"""
from functools import wraps
from django.shortcuts import render, redirect
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
                return redirect('accounts:login')
            if request.user.role != role:
                return render(request, 'dashboard/error.html', {
                    'error_title': 'Access Denied',
                    'error_message': f"You don't have permission to access this page. Required role: {role}",
                    'error_code': 403,
                }, status=403)
            return view_func(request, *args, **kwargs)
        wrapper.__wrapped__ = view_func
        return login_required(wrapper)
    return decorator


def superadmin_required(view_func):
    """Require SUPER_ADMIN role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'SUPER_ADMIN':
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Super Administrator privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def admin_required(view_func):
    """Require SUPER_ADMIN or PLATFORM_ADMIN role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Administrator privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def analyst_required(view_func):
    """Require MEMBER role (analyst)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'MEMBER':
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Analyst privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def requester_required(view_func):
    """Require REQUESTER role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'REQUESTER':
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Requester privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def client_required(view_func):
    """Require CLIENT role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role != 'CLIENT':
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Client privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def finance_required(view_func):
    """Require FINANCE or SUPER_ADMIN role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role not in ('FINANCE', 'SUPER_ADMIN'):
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Finance privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


def staff_required(view_func):
    """Require any staff role (SUPER_ADMIN, PLATFORM_ADMIN, MEMBER, FINANCE)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER', 'FINANCE'):
            return render(request, 'dashboard/error.html', {
                'error_title': 'Access Denied',
                'error_message': 'You need Staff privileges to access this page.',
                'error_code': 403,
            }, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)
