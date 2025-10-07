# app/services/bg_removal.py
import io
from PIL import Image
from rembg import remove

def remove_background(image_bytes: bytes) -> bytes:
    """
    Removes the background from image bytes using rembg.
    Returns PNG bytes with a transparent background.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        out = remove(img)
        if isinstance(out, bytes):
            return out
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        raise RuntimeError(f"Background removal failed: {e}")
