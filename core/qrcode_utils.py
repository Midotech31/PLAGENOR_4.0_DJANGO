import qrcode
import io
import base64


def generate_qr_base64(data: str, version=1, box_size=8, border=2, fill_color="#1E293B", back_color="white") -> str:
    """Generate a QR code and return as base64-encoded PNG string."""
    qr = qrcode.QRCode(version=version, box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def generate_qr_data_url(data: str) -> str:
    """Generate a QR code and return as a data URL for embedding in HTML."""
    b64 = generate_qr_base64(data)
    return f"data:image/png;base64,{b64}"


def generate_request_tracking_qr(request_obj, base_url=None) -> str:
    """
    Generate QR code for request tracking.
    
    Args:
        request_obj: Request model instance
        base_url: Base URL for the tracking link (optional)
    
    Returns:
        Data URL for embedding in HTML
    """
    if not request_obj.guest_token:
        return None
    
    if base_url:
        tracking_url = f"{base_url}/track/{request_obj.guest_token}/"
    else:
        tracking_url = f"/track/{request_obj.guest_token}/"
    
    return generate_qr_data_url(tracking_url)


def generate_ibtikar_id_qr(request_obj, base_url=None) -> str:
    """
    Generate QR code for IBTIKAR ID tracking.
    
    Args:
        request_obj: Request model instance
        base_url: Base URL for the tracking link (optional)
    
    Returns:
        Data URL for embedding in HTML
    """
    if not request_obj.guest_token:
        return None
    
    if base_url:
        tracking_url = f"{base_url}/ibtikar/{request_obj.guest_token}/"
    else:
        tracking_url = f"/ibtikar/{request_obj.guest_token}/"
    
    return generate_qr_data_url(tracking_url)


def generate_report_qr(request_obj, base_url=None) -> str:
    """
    Generate QR code for report access.
    
    Args:
        request_obj: Request model instance
        base_url: Base URL for the report link (optional)
    
    Returns:
        Data URL for embedding in HTML
    """
    if not request_obj.report_token:
        return None
    
    if base_url:
        report_url = f"{base_url}/report/{request_obj.report_token}/"
    else:
        report_url = f"/report/{request_obj.report_token}/"
    
    return generate_qr_data_url(report_url)


def generate_reception_qr(request_obj, base_url=None) -> str:
    """
    Generate QR code for sample reception tracking.
    
    Args:
        request_obj: Request model instance
        base_url: Base URL for the tracking link (optional)
    
    Returns:
        Data URL for embedding in HTML
    """
    if not request_obj.guest_token:
        return None
    
    if base_url:
        reception_url = f"{base_url}/reception/{request_obj.guest_token}/"
    else:
        reception_url = f"/reception/{request_obj.guest_token}/"
    
    return generate_qr_data_url(reception_url)


def get_tracking_info(request_obj) -> dict:
    """
    Get all tracking information for a request.
    
    Returns:
        Dict with all QR code data URLs and tracking IDs
    """
    info = {
        'display_id': request_obj.display_id,
        'guest_token': str(request_obj.guest_token) if request_obj.guest_token else None,
        'report_token': str(request_obj.report_token) if request_obj.report_token else None,
        'has_tracking_qr': False,
        'has_report_qr': False,
    }
    
    if request_obj.guest_token:
        info['has_tracking_qr'] = True
        info['tracking_url'] = f"/track/{request_obj.guest_token}/"
        info['tracking_qr'] = generate_qr_data_url(info['tracking_url'])
    
    if request_obj.report_token:
        info['has_report_qr'] = True
        info['report_url'] = f"/report/{request_obj.report_token}/"
        info['report_qr'] = generate_qr_data_url(info['report_url'])
    
    return info
