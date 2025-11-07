import io
import logging
import numpy as np
import cv2
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from rembg import remove, new_session

try:
    _SESSION = new_session("u2net_human_seg")
except Exception:
    _SESSION = None

logger = logging.getLogger("bg_removal")

MAX_WORKERS = 6
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def _process_single_image(image_bytes: bytes) -> bytes:
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
        if img_bgr is None:
            raise ValueError("Invalid or unsupported image.")

        if img_bgr.shape[2] == 3:
            img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
        elif img_bgr.shape[2] == 4:
            img_rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2RGBA)
        else:
            raise ValueError("Unsupported channel count.")

        h, w = img_rgba.shape[:2]
        max_dim = 1024
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img_rgba = cv2.resize(img_rgba, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        pil_img = Image.fromarray(img_rgba, mode="RGBA")

        out = remove(pil_img, session=_SESSION) if _SESSION else remove(pil_img)

        if isinstance(out, bytes):
            return out

        buf = io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    except Exception as e:
        logger.error(f"Background removal failed: {e}")
        raise RuntimeError(f"Background removal failed: {e}")


def remove_background(image_bytes: bytes) -> bytes:
    return _process_single_image(image_bytes)


def remove_background_batch(images: list[bytes]) -> list[bytes]:
    if not images:
        return []

    futures = []
    results = [None] * len(images)

    for i, img_bytes in enumerate(images):
        futures.append(_executor.submit(_process_single_image, img_bytes))

    for i, future in enumerate(as_completed(futures)):
        try:
            results[i] = future.result()
        except Exception as e:
            logger.error(f"Image {i+1} failed: {e}")
            results[i] = None

    return [r for r in results if r is not None]
