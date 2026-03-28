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
    # For now, all role dashboards redirect to a placeholder
    # Each role-specific view will be implemented in future tasks
    target = routes.get(role, 'dashboard:requester')
    try:
        return redirect(target)
    except Exception:
        return redirect('dashboard:placeholder')


@login_required
def placeholder_dashboard(request):
    from django.shortcuts import render
    return render(request, 'dashboard/placeholder.html')
