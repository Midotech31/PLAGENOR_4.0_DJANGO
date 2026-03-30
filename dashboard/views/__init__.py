from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def dashboard_router(request):
    role = request.user.role
    routes = {
        'SUPER_ADMIN': 'dashboard:superadmin',
        'PLATFORM_ADMIN': 'dashboard:admin_ops',
        'MEMBER': 'dashboard:analyst',
        'FINANCE': 'dashboard:finance',
        'REQUESTER': 'dashboard:requester',
        'CLIENT': 'dashboard:client',
    }
    target = routes.get(role, 'dashboard:requester')
    return redirect(target)
