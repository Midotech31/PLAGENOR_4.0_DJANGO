from django.urls import reverse


def workspace_context(request):
    active_account = request.user.is_authenticated and request.user.is_active
    return {
        'workspace_base': 'base.html' if active_account else 'base_public.html',
        'workspace_url': (
            reverse('dashboard:router') if active_account
            else reverse('guest_submit') + '?channel=IBTIKAR'
        ),
    }
