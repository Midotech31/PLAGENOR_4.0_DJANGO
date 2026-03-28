from django.shortcuts import render
from core.models import Service, Request


def home(request):
    services = Service.objects.filter(active=True)[:8]
    return render(request, 'pages/home.html', {'services': services})


def about(request):
    return render(request, 'pages/about.html')


def services(request):
    services = Service.objects.filter(active=True)
    return render(request, 'pages/services.html', {'services': services})


def track(request):
    tracked_request = None
    q = request.GET.get('q', '').strip()
    if q:
        tracked_request = Request.objects.filter(display_id__iexact=q).first()
        if not tracked_request:
            try:
                import uuid
                token = uuid.UUID(q)
                tracked_request = Request.objects.filter(guest_token=token).first()
            except (ValueError, AttributeError):
                pass
    return render(request, 'pages/track.html', {'tracked_request': tracked_request})
