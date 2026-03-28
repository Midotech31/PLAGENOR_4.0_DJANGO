import qrcode
import io
import base64


def generate_qr_base64(data: str) -> str:
    """Generate a QR code and return as base64-encoded PNG string."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E293B", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def generate_qr_data_url(data: str) -> str:
    """Generate a QR code and return as a data URL for embedding in HTML."""
    b64 = generate_qr_base64(data)
    return f"data:image/png;base64,{b64}"
