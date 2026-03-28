from django.shortcuts import redirect


def redirect_back(request, fallback_url='dashboard:router'):
    """Redirect to the referring page, preserving tab context."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    return redirect(fallback_url)
