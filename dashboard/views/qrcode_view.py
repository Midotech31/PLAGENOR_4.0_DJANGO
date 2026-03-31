"""QR code generator view — returns a PNG QR code image for a request's report page."""
import io
import qrcode
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from core.models import Request


@login_required
def report_qr(request, pk):
    """Generate QR code PNG linking to the public report detail page."""
    req = Request.objects.filter(pk=pk).first()
    if not req:
        raise Http404

    # Only admin and assigned analyst can see QR
    if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
        if request.user.role == 'MEMBER':
            try:
                if req.assigned_to != request.user.member_profile:
                    raise Http404
            except (AttributeError, ObjectDoesNotExist):
                # Member profile not found or no assignment
                raise Http404
        else:
            raise Http404

    # Ensure report_token exists
    if not req.report_token:
        import uuid
        req.report_token = uuid.uuid4()
        req.save(update_fields=['report_token'])

    # Build the public report detail URL (includes embedded report)
    report_url = request.build_absolute_uri(f'/report/{req.report_token}/detail/')

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(report_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1e293b', back_color='#ffffff')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return HttpResponse(buffer.getvalue(), content_type='image/png')
