# app/services/fill_black_bg.py
import io
from PIL import Image

def fill_black_background(image_bytes: bytes) -> bytes:
    """
    Takes PNG image bytes (with transparency) and fills
    transparent areas with solid black.
    Returns image bytes (JPEG format, no transparency).
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Create a black background image
    black_bg = Image.new("RGB", img.size, (0, 0, 0))

    # Paste the original image onto black background using alpha channel as mask
    black_bg.paste(img, mask=img.split()[3])  # 3 = alpha channel

    # Save to bytes as JPEG (since JPEG has no transparency)
    buf = io.BytesIO()
    black_bg.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
