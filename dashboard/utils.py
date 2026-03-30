from django.shortcuts import redirect
from django.urls import NoReverseMatch


def redirect_back(request, fallback_url='dashboard:router'):
    """Redirect to the referring page, preserving tab context."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    try:
        return redirect(fallback_url)
    except NoReverseMatch:
        # URL pattern not found - redirect to home
        return redirect('/')
