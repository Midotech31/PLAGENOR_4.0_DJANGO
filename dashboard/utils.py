from django.shortcuts import redirect


def safe_int(value, default=0):
    """Parse an int from untrusted input, falling back to `default`."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    """Parse a float from untrusted input, falling back to `default`."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def redirect_back(request, fallback_url='dashboard:router'):
    """Redirect to the referring page, preserving tab context."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    try:
        return redirect(fallback_url)
    except Exception:
        return redirect('/')
