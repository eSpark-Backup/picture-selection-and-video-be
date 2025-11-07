import io
import logging
import numpy as np
import cv2
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("fill_black_bg")

MAX_WORKERS = 6
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

try:
    _HAS_CUDA = cv2.cuda.getCudaEnabledDeviceCount() > 0
except Exception:
    _HAS_CUDA = False


def _process_single_image(image_bytes: bytes) -> bytes:
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)

        if img is None:
            raise ValueError("Invalid or unsupported image data")

        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

        h, w = img.shape[:2]
        max_dim = 1024
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        alpha = img[:, :, 3].astype(np.float32) / 255.0
        rgb = img[:, :, :3].astype(np.float32)

        blended = (rgb * alpha[..., None]).astype(np.uint8)

        if _HAS_CUDA:
            try:
                gpu_img = cv2.cuda_GpuMat()
                gpu_img.upload(blended)
                blended = gpu_img.download()
            except Exception:
                pass

        success, encoded = cv2.imencode(".jpg", blended, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not success:
            raise RuntimeError("Failed to encode image as JPEG")

        return encoded.tobytes()

    except Exception as e:
        logger.error(f"Black background fill failed: {e}")
        raise RuntimeError(f"Black background fill failed: {e}")


def fill_black_background(image_bytes: bytes) -> bytes:
    return _process_single_image(image_bytes)


def fill_black_background_batch(images: list[bytes]) -> list[bytes]:
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
