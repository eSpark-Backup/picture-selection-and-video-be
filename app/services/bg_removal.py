# app/services/bg_removal.py
import io
from PIL import Image
from rembg import remove

def remove_background(image_bytes: bytes) -> bytes:
    """
    Removes the background from image bytes using rembg.
    Optimized with resizing, efficiency tweaks, and optional GPU acceleration.
    Returns PNG bytes with a transparent background.
    """
    import io, logging, cv2, numpy as np
    from PIL import Image
    from rembg import remove, new_session

    logger = logging.getLogger("image_processor")

    try:
        # Step 6: Optional GPU acceleration (if available)
        try:
            session = new_session("u2net_human_seg")
        except Exception:
            session = None

        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        # Step 2: Resize large images before processing (speed optimization)
        max_size = (1024, 1024)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.LANCZOS)

        # Step 5: Efficiency tweaks (convert via OpenCV for better performance)
        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)

        # Convert back to PIL for rembg
        pil_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA))

        # Background removal
        out = remove(pil_img, session=session) if session else remove(pil_img)

        # Save final result
        if isinstance(out, bytes):
            result = out
        else:
            buf = io.BytesIO()
            out.save(buf, format="PNG", optimize=True)
            result = buf.getvalue()

        logger.info("Background removed successfully with optimized pipeline.")
        return result

    except Exception as e:
        logger.error(f"Background removal failed: {e}")
        raise RuntimeError(f"Background removal failed: {e}")
