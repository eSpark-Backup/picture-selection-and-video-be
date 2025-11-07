import cv2
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("face_detection")

MAX_WORKERS = 6
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

try:
    CPU_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except Exception as e:
    logger.error(f"Failed to load Haar cascade: {e}")
    CPU_CASCADE = None

try:
    _HAS_CUDA = cv2.cuda.getCudaEnabledDeviceCount() > 0
    if _HAS_CUDA:
        GPU_CASCADE = cv2.cuda_CascadeClassifier.create(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    else:
        GPU_CASCADE = None
except Exception:
    _HAS_CUDA = False
    GPU_CASCADE = None

def _process_single_image(image_bytes: bytes) -> bytes:
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Invalid image data")

        h, w = img.shape[:2]
        if w > 1024:
            scale = 1024 / w
            img = cv2.resize(img, (1024, int(h * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        faces = []
        used_gpu = False
        if _HAS_CUDA and GPU_CASCADE is not None:
            try:
                gpu_gray = cv2.cuda_GpuMat()
                gpu_gray.upload(gray)
                faces_buf = GPU_CASCADE.detectMultiScale(gpu_gray)
                if faces_buf is not None:
                    faces = faces_buf.download()
                    used_gpu = True
            except Exception:
                used_gpu = False
                faces = []

        if not faces or len(faces) == 0:
            if CPU_CASCADE is None:
                raise RuntimeError("No CPU face cascade available")
            faces = CPU_CASCADE.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
            )

        # Draw bounding boxes (optional, uncomment if visualization needed)
        # for (x, y, w, h) in faces:
        #     cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        success, encoded_img = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not success:
            raise RuntimeError("Failed to encode image to JPEG")

        logger.info(f"Faces detected: {len(faces)} (GPU={used_gpu})")
        return encoded_img.tobytes()

    except Exception as e:
        logger.error(f"Face detection failed: {e}")
        raise RuntimeError(f"Face detection failed: {e}")


def detect_faces(image_bytes: bytes) -> bytes:
    return _process_single_image(image_bytes)


def detect_faces_batch(images: list[bytes]) -> list[bytes]:
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
            logger.error(f"Face detection failed for image {i + 1}: {e}")
            results[i] = None

    return [r for r in results if r is not None]
